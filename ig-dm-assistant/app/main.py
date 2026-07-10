"""Instagram DM Assistant — FastAPI entry point.

Endpoints:
  GET  /webhook            Meta verification handshake
  POST /webhook            inbound message events (HMAC-verified)
  GET  /dashboard          the approval PWA (login-gated client-side)
  POST /api/login          password login → session cookie
  GET  /api/state          pending drafts + history
  GET  /api/events         SSE stream of new messages/drafts
  POST /api/drafts/{id}/approve|edit|skip
  POST /api/push/subscribe Web Push subscription registration
  GET  /healthz            health check
"""

import asyncio
import json
import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import auth, config, db, events, meta_api, pipeline

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Instagram DM Assistant", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def startup() -> None:
    db.init()
    asyncio.create_task(pipeline.worker())
    log.info("started — model=%s", config.CLAUDE_MODEL)


# ── Meta webhook ─────────────────────────────────────────────────────────────

@app.get("/webhook")
async def webhook_verify(request: Request):
    params = request.query_params
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == config.META_VERIFY_TOKEN):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.body()
    if not meta_api.verify_signature(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="bad signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="bad json")

    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue  # our own outbound messages echoed back
            text = message.get("text")
            sender_id = (event.get("sender") or {}).get("id")
            if not (text and sender_id):
                continue  # attachments/reactions — handle in the IG app
            pipeline.enqueue(sender_id, text, message.get("mid"),
                             event.get("timestamp"))
    return {"status": "ok"}


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/login")
async def login(request: Request, response: Response):
    form = await request.json()
    if not auth.check_password(form.get("password", "")):
        raise HTTPException(status_code=401, detail="wrong password")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.COOKIE_NAME, auth.make_session_cookie(),
        max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax", secure=True,
    )
    return response


@app.get("/api/me")
async def me(request: Request):
    return {"authenticated": auth.is_authenticated(request),
            "vapid_public_key": config.VAPID_PUBLIC_KEY}


# ── Dashboard API ────────────────────────────────────────────────────────────

@app.get("/api/state", dependencies=[Depends(auth.require_auth)])
async def state():
    return {"pending": db.pending_drafts(), "history": db.draft_history()}


@app.get("/api/events")
async def sse(request: Request):
    if not auth.is_authenticated(request):
        raise HTTPException(status_code=401)

    async def stream():
        q = events.subscribe()
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


async def _send_reply(draft: dict, text: str, status: str):
    try:
        await meta_api.send_text(draft["sender_id"], text)
    except Exception as e:
        log.error("send failed for draft %s: %s", draft["id"], e)
        db.resolve_draft(draft["id"], "failed", text)
        events.broadcast("resolved", {"id": draft["id"], "status": "failed"})
        raise HTTPException(status_code=502, detail=f"send failed: {e}")
    db.add_message(draft["sender_id"], "out", text)
    db.resolve_draft(draft["id"], status, text)
    events.broadcast("resolved", {"id": draft["id"], "status": status})


def _pending_draft_or_404(draft_id: int) -> dict:
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404)
    if draft["status"] != "pending":
        raise HTTPException(status_code=409, detail="already resolved")
    return draft


@app.post("/api/drafts/{draft_id}/approve", dependencies=[Depends(auth.require_auth)])
async def approve(draft_id: int):
    draft = _pending_draft_or_404(draft_id)
    await _send_reply(draft, draft["draft_text"], "approved")
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/edit", dependencies=[Depends(auth.require_auth)])
async def edit(draft_id: int, request: Request):
    draft = _pending_draft_or_404(draft_id)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty reply")
    # Edited drafts are gold: original + correction stored for future few-shots
    await _send_reply(draft, text, "edited")
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/skip", dependencies=[Depends(auth.require_auth)])
async def skip(draft_id: int):
    draft = _pending_draft_or_404(draft_id)
    db.resolve_draft(draft_id, "skipped")
    events.broadcast("resolved", {"id": draft_id, "status": "skipped"})
    return {"ok": True}


@app.post("/api/push/subscribe", dependencies=[Depends(auth.require_auth)])
async def push_subscribe(request: Request):
    sub = await request.json()
    if not sub.get("endpoint"):
        raise HTTPException(status_code=400, detail="invalid subscription")
    db.add_push_subscription(sub)
    return {"ok": True}


# ── Static / PWA ─────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"ok": True, "time": time.time()}


@app.get("/")
@app.get("/dashboard")
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sw.js")
async def service_worker():
    # Served from the root scope so the SW can control the whole app
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.json",
                        media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
