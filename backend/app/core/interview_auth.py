"""Candidate interview-session token auth.

This is a deliberately separate authentication boundary from the recruiter JWT
(`app/core/auth.py` / `app/api/deps.py`). A candidate proves session ownership
with an opaque random token that appears only in the interview URL. The server
stores only a salted SHA-256 hash of that token, never the raw value.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Path

from app.core.config import settings
from app.core.database import get_db


def _secret() -> str:
    return settings.INTERVIEW_TOKEN_SECRET or os.getenv("SECRET_KEY", "hireonomous-interview-fallback-secret")


def generate_interview_token() -> str:
    """Cryptographically secure, URL-safe, no DB identifiers embedded."""
    return secrets.token_urlsafe(32)


def hash_interview_token(token: str) -> str:
    """Salted keyed hash so a DB leak cannot be reversed without the app secret."""
    return hmac.new(_secret().encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def token_expiry() -> datetime:
    return datetime.utcnow() + timedelta(hours=settings.INTERVIEW_TOKEN_TTL_HOURS)


async def resolve_interview_by_token(token: str, *, require_active: bool = False) -> dict:
    """Look up the interview a token belongs to. Raises HTTPException on any
    validation failure. `require_active` additionally rejects terminal / expired
    sessions (used by /start and /turn, not by the read-only session info route)."""
    from app.models.interview import TERMINAL_STATUSES

    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="Interview not found")

    db = get_db()
    token_hash = hash_interview_token(token)
    interview = await db.interviews.find_one({"token_hash": token_hash})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    expires_at = interview.get("token_expires_at")
    if expires_at and isinstance(expires_at, datetime) and datetime.utcnow() > expires_at:
        if interview.get("status") not in ("completed", "cancelled"):
            await db.interviews.update_one(
                {"id": interview["id"], "status": {"$nin": TERMINAL_STATUSES}},
                {"$set": {"status": "expired", "updated_at": datetime.utcnow()}},
            )
        raise HTTPException(status_code=410, detail="This interview link has expired. Please contact the recruiter.")

    if interview.get("status") == "cancelled":
        raise HTTPException(status_code=410, detail="This interview has been cancelled.")

    if require_active:
        if interview.get("status") == "completed":
            raise HTTPException(status_code=409, detail="This interview has already been completed.")
        if interview.get("status") in ("expired", "failed"):
            raise HTTPException(status_code=410, detail="This interview is no longer available.")

    return interview
