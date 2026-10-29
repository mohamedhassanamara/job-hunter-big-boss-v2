"""The browser extension's local token (docs/LINKEDIN_EXTENSION_DESIGN.md §2.5).

Created in Settings → LinkedIn, shown once; only its SHA-256 is stored (`app_setting` key
`extension_auth`, never returned by the settings API). The token opens `/api/ext/*` and nothing
else. One token at a time: creating a new one replaces (revokes) the old one."""

import hashlib
import hmac
import re
import secrets
from typing import Any

from sqlmodel import Session, select

from app.models import AppSetting
from app.models.base import utcnow

KEY = "extension_auth"
ID_PATTERN = re.compile(r"^[a-p]{32}$")  # a Chromium extension id


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _row(session: Session) -> AppSetting | None:
    return session.exec(select(AppSetting).where(AppSetting.key == KEY)).first()


def create(session: Session) -> str:
    """A new token (the old one stops working). The plain text is returned once, never stored."""
    token = secrets.token_urlsafe(32)
    value: dict[str, Any] = {"sha256": _digest(token), "created_at": utcnow().isoformat(),
                             "last_used_at": None}
    row = _row(session)
    if row is None:
        session.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
        session.add(row)
    session.commit()
    return token


def revoke(session: Session) -> None:
    row = _row(session)
    if row is not None:
        session.delete(row)
        session.commit()


def status(session: Session) -> dict[str, Any]:
    row = _row(session)
    if row is None or not row.value.get("sha256"):
        return {"exists": False, "created_at": None, "last_used_at": None}
    return {"exists": True, "created_at": row.value.get("created_at"),
            "last_used_at": row.value.get("last_used_at")}


def verify(session: Session, token: str) -> bool:
    row = _row(session)
    if row is None or not token:
        return False
    stored = str(row.value.get("sha256") or "")
    return bool(stored) and hmac.compare_digest(stored, _digest(token))


def touch(session: Session) -> None:
    """Remember when the extension last connected (shown in Settings)."""
    row = _row(session)
    if row is not None:
        row.value = {**row.value, "last_used_at": utcnow().isoformat()}
        session.add(row)
        session.commit()


def origin_regex(ids: list[str]) -> str | None:
    """CORS: exactly these extension origins, no wildcard. Malformed ids are dropped."""
    good = [i for i in dict.fromkeys(ids) if ID_PATTERN.match(i)]
    return rf"^chrome-extension://({'|'.join(good)})$" if good else None
