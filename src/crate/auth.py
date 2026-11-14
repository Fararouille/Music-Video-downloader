from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

from .config import Settings

SESSION_COOKIE = "crate_session"


def session_value(token: str) -> str:
    return hmac.new(token.encode("utf-8"), b"crate-session-v1", hashlib.sha256).hexdigest()


def authenticated(settings: Settings, request: Request) -> bool:
    if not settings.token:
        return True
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return hmac.compare_digest(header[7:].strip(), settings.token)
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie, session_value(settings.token))
