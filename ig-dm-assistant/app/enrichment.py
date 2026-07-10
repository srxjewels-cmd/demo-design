"""Customer enrichment: Apollo (CRM) + Shopify (orders), cached 24h per sender."""

import logging

import httpx

from . import config, db

log = logging.getLogger("enrichment")


async def _apollo_lookup(name: str | None, email: str | None = None) -> dict | None:
    """Search Apollo contacts by name/email. Returns a trimmed contact dict or None."""
    if not config.APOLLO_API_KEY or not (name or email):
        return None
    body: dict = {"page": 1, "per_page": 3}
    if email:
        body["q_keywords"] = email
    elif name:
        body["q_keywords"] = name
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.apollo.io/api/v1/contacts/search",
                headers={"X-Api-Key": config.APOLLO_API_KEY,
                         "Content-Type": "application/json"},
                json=body,
            )
        if r.status_code != 200:
            log.info("apollo search failed (%s): %s", r.status_code, r.text[:200])
            return None
        contacts = r.json().get("contacts") or []
        if not contacts:
            return None
        c = contacts[0]
        return {
            "name": c.get("name"),
            "email": c.get("email"),
            "title": c.get("title"),
            "organization": (c.get("organization") or {}).get("name"),
            "phone": (c.get("phone_numbers") or [{}])[0].get("raw_number")
                     if c.get("phone_numbers") else None,
        }
    except httpx.HTTPError as e:
        log.info("apollo error: %s", e)
        return None


async def _shopify_lookup(name: str | None, email: str | None = None) -> dict | None:
    """Find the Shopify customer and pull recent orders + fulfillment status."""
    if not (config.SHOPIFY_TOKEN and config.SHOPIFY_STORE) or not (name or email):
        return None
    base = f"https://{config.SHOPIFY_STORE}.myshopify.com/admin/api/2024-10"
    headers = {"X-Shopify-Access-Token": config.SHOPIFY_TOKEN}
    query = email or name
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            r = await client.get(f"{base}/customers/search.json",
                                 params={"query": query, "limit": 1})
            if r.status_code != 200:
                log.info("shopify customer search failed (%s)", r.status_code)
                return None
            customers = r.json().get("customers") or []
            if not customers:
                return None
            cust = customers[0]

            r = await client.get(
                f"{base}/orders.json",
                params={"customer_id": cust["id"], "status": "any", "limit": 5,
                        "fields": "name,created_at,total_price,currency,"
                                  "fulfillment_status,financial_status,line_items"},
            )
            orders = r.json().get("orders", []) if r.status_code == 200 else []

        return {
            "customer_id": cust["id"],
            "name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip(),
            "email": cust.get("email"),
            "total_spent": cust.get("total_spent"),
            "orders_count": cust.get("orders_count"),
            "orders": [
                {
                    "name": o.get("name"),
                    "created_at": o.get("created_at"),
                    "total": f"{o.get('total_price')} {o.get('currency')}",
                    "financial_status": o.get("financial_status"),
                    "fulfillment_status": o.get("fulfillment_status") or "unfulfilled",
                    "items": [li.get("title") for li in (o.get("line_items") or [])][:5],
                }
                for o in orders
            ],
        }
    except httpx.HTTPError as e:
        log.info("shopify error: %s", e)
        return None


async def enrich(sender_id: str, display_name: str | None) -> dict:
    """CRM + order context for a sender. Cached for 24h to avoid repeated calls."""
    cached = db.cache_get(sender_id)
    if cached is not None:
        return cached

    apollo = await _apollo_lookup(display_name)
    email = (apollo or {}).get("email")
    shopify = await _shopify_lookup(display_name, email)

    data = {
        "apollo": apollo,
        "shopify": shopify,
        "is_new_customer": apollo is None and shopify is None,
    }
    db.cache_set(sender_id, data)
    return data


def summarize(profile: dict) -> str:
    """Two-line CRM summary for the dashboard card."""
    if profile.get("is_new_customer"):
        return "New customer — no CRM or order history found."
    parts = []
    shop = profile.get("shopify")
    if shop:
        parts.append(f"{shop.get('orders_count', 0)} orders, "
                     f"{shop.get('total_spent', '0')} lifetime spend")
        if shop.get("orders"):
            o = shop["orders"][0]
            parts.append(f"Last order {o['name']}: {o['fulfillment_status']}, {o['total']}")
    apollo = profile.get("apollo")
    if apollo and apollo.get("organization"):
        parts.append(f"{apollo.get('title') or 'Contact'} at {apollo['organization']}")
    return " · ".join(parts) or "Known contact — limited data."
