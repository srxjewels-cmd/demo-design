"""Inbound message pipeline: store → enrich → draft → notify dashboard."""

import asyncio
import logging
import time

from . import db, drafting, enrichment, events, meta_api, push

log = logging.getLogger("pipeline")

_queue: asyncio.Queue = asyncio.Queue()


def enqueue(sender_id: str, text: str, mid: str | None, timestamp_ms: int | None) -> None:
    _queue.put_nowait({
        "sender_id": sender_id,
        "text": text,
        "mid": mid,
        "timestamp": (timestamp_ms or 0) / 1000 or time.time(),
    })


async def worker() -> None:
    while True:
        item = await _queue.get()
        try:
            await _process(item)
        except Exception:
            log.exception("failed to process message from %s", item["sender_id"])
        finally:
            _queue.task_done()


async def _process(item: dict) -> None:
    sender_id, text = item["sender_id"], item["text"]

    db.upsert_conversation(sender_id, customer_msg_at=item["timestamp"])
    message_id = db.add_message(sender_id, "in", text, mid=item["mid"])
    if message_id is None:
        return  # duplicate delivery of the same mid

    # Profile (name + avatar) — best effort
    convo = db.get_conversation(sender_id) or {}
    if not convo.get("name"):
        profile = await meta_api.fetch_profile(sender_id)
        if profile:
            db.upsert_conversation(sender_id, name=profile.get("name"),
                                   profile_pic=profile.get("profile_pic"))
            convo = db.get_conversation(sender_id) or {}

    display_name = convo.get("name")
    events.broadcast("message", {
        "sender_id": sender_id, "name": display_name, "text": text,
    })

    # CRM + orders (cached 24h)
    crm = await enrichment.enrich(sender_id, display_name)
    crm_summary = enrichment.summarize(crm)

    # Claude draft
    try:
        draft_text, flagged, flag_reason = await drafting.generate_draft(
            sender_id, text, crm, crm_summary
        )
    except Exception as e:
        log.exception("draft generation failed")
        draft_text = "(Draft generation failed — write your own reply.)"
        flagged, flag_reason = True, f"error: {type(e).__name__}"

    draft_id = db.create_draft(sender_id, message_id, draft_text,
                               flagged, flag_reason, crm_summary)

    card = {
        "id": draft_id,
        "sender_id": sender_id,
        "name": display_name or sender_id,
        "profile_pic": convo.get("profile_pic"),
        "customer_message": text,
        "draft_text": draft_text,
        "flagged": flagged,
        "flag_reason": flag_reason,
        "crm_summary": crm_summary,
        "created_at": time.time(),
    }
    events.broadcast("draft", card)

    prefix = "⚠️ " if flagged else ""
    await push.notify(
        title=f"{prefix}New DM from {display_name or 'a customer'}",
        body=text[:120],
    )
