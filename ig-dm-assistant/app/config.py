"""Central configuration, read once from environment variables."""

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Meta / Instagram
META_PAGE_TOKEN = _env("META_PAGE_TOKEN")
META_APP_SECRET = _env("META_APP_SECRET")
META_VERIFY_TOKEN = _env("META_VERIFY_TOKEN")
META_GRAPH_VERSION = _env("META_GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# Anthropic
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-4-6")

# CRM / Store
APOLLO_API_KEY = _env("APOLLO_API_KEY")
SHOPIFY_TOKEN = _env("SHOPIFY_TOKEN")
SHOPIFY_STORE = _env("SHOPIFY_STORE")

# Dashboard
DASHBOARD_PASSWORD = _env("DASHBOARD_PASSWORD")
SESSION_SECRET = _env("SESSION_SECRET", "change-me")

# Web push
VAPID_PUBLIC_KEY = _env("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = _env("VAPID_PRIVATE_KEY")
VAPID_CLAIM_EMAIL = _env("VAPID_CLAIM_EMAIL", "mailto:admin@example.com")

# Storage
DB_PATH = _env("DB_PATH", "data/assistant.db")

# Safety
SENSITIVE_REFUND_THRESHOLD = float(_env("SENSITIVE_REFUND_THRESHOLD", "100") or 100)

# Cache TTL for CRM lookups (seconds)
CUSTOMER_CACHE_TTL = 24 * 60 * 60

# Meta's standard messaging window (seconds)
META_REPLY_WINDOW = 24 * 60 * 60
