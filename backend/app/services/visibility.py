"""Which contact details are printed on output documents (Settings → Candidate).

`app_setting.output_visibility = {show_phone, show_location}`, both on by default. It only
changes what a CV header, cover letter or signature shows. Matching, scoring, the verifier and
every other internal reader keep using the stored profile values.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models.settings import AppSetting

KEY = "output_visibility"
DEFAULTS: dict[str, bool] = {"show_phone": True, "show_location": True}


def normalize(value: Any) -> dict[str, bool]:
    """A stored value (or nothing) as the two flags; anything but an explicit False is on."""
    raw = value if isinstance(value, dict) else {}
    return {k: raw.get(k, default) is not False for k, default in DEFAULTS.items()}


def load(s: Session) -> dict[str, bool]:
    row = s.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
    return normalize(row.value if row else None)


def check(value: Any) -> None:
    """Validation for PUT /settings/output_visibility (raises ValueError)."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS) \
            or not all(isinstance(v, bool) for v in value.values()):
        raise ValueError("output_visibility takes show_phone and show_location, each true or false")
