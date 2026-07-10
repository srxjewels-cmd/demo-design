"""Meta Graph API: webhook signature verification, profile lookup, sending replies.

Path B note: to swap in Respond.io, replace send_text() with a POST to
https://api.respond.io/v2/contact/{id}/message and drop the signature check
in favour of Respond.io's webhook token header. Nothing else changes.
"""

import hashlib
import hmac
import logging
import time

import httpx

from . import config, db

log = logging.getLogger("meta")


def verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 (sha256 HMAC of the raw body with the app secret)."""
    if not config.META_APP_SECRET:
        log.warning("META_APP_SECRET not set — rejecting webhook")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[len("sha256="):])


async def fetch_profile(psid: str) -> dict:
    """Best-effort name + avatar for the sender. Returns {} on failure."""
    if not config.META_PAGE_TOKEN:
        return {}
    url = f"{config.GRAPH_BASE}/{psid}"
    params = {"fields": "name,profile_pic", "access_token": config.META_PAGE_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            log.info("profile lookup failed (%s): %s", r.status_code, r.text[:200])
    except httpx.HTTPError as e:
        log.info("profile lookup error: %s", e)
    return {}


def _within_reply_window(sender_id: str) -> bool:
    convo = db.get_conversation(sender_id)
    last = (convo or {}).get("last_customer_msg_at")
    return bool(last) and (time.time() - last) < config.META_REPLY_WINDOW


async def send_text(sender_id: str, text: str) -> dict:
    """Send a reply via the Send API.

    Inside the 24h window a standard RESPONSE message is used; outside it we fall
    back to the HUMAN_AGENT tag (requires that permission from App Review, allows
    replies up to 7 days after the customer's last message).
    """
    if not config.META_PAGE_TOKEN:
        raise RuntimeError("META_PAGE_TOKEN not configured")

    payload: dict = {
        "recipient": {"id": sender_id},
        "message": {"text": text},
    }
    if _within_reply_window(sender_id):
        payload["messaging_type"] = "RESPONSE"
    else:
        payload["messaging_type"] = "MESSAGE_TAG"
        payload["tag"] = "HUMAN_AGENT"

    url = f"{config.GRAPH_BASE}/me/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, params={"access_token": config.META_PAGE_TOKEN},
                              json=payload)
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"Meta send failed: {data}")
    return data
