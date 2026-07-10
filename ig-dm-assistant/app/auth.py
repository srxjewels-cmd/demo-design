"""Single-user session auth for the dashboard (signed cookie)."""

import hmac

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, TimestampSigner

from . import config

COOKIE_NAME = "dm_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days

_signer = TimestampSigner(config.SESSION_SECRET)


def check_password(password: str) -> bool:
    return bool(config.DASHBOARD_PASSWORD) and hmac.compare_digest(
        password, config.DASHBOARD_PASSWORD
    )


def make_session_cookie() -> str:
    return _signer.sign(b"owner").decode()


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        _signer.unsign(token, max_age=SESSION_MAX_AGE)
        return True
    except BadSignature:
        return False


def require_auth(request: Request) -> None:
    """FastAPI dependency — 401 for API calls without a valid session."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="not authenticated")
