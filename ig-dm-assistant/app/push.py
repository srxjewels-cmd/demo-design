"""Web Push notifications (VAPID) to the installed PWA."""

import asyncio
import json
import logging

from . import config, db

log = logging.getLogger("push")


def _send_one(subscription: dict, payload: str) -> bool:
    """Returns False if the subscription is dead and should be removed."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=config.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.VAPID_CLAIM_EMAIL},
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            return False  # endpoint gone
        log.info("push failed: %s", e)
        return True


async def notify(title: str, body: str, url: str = "/dashboard") -> None:
    if not (config.VAPID_PRIVATE_KEY and config.VAPID_PUBLIC_KEY):
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    subs = db.list_push_subscriptions()
    if not subs:
        return
    loop = asyncio.get_running_loop()
    for entry in subs:
        alive = await loop.run_in_executor(None, _send_one, entry["subscription"], payload)
        if not alive:
            db.remove_push_subscription(entry["id"])
