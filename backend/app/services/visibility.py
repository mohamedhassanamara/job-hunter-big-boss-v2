"""Which contact details are printed on output documents (Settings → Candidate).

`app_setting.output_visibility = {show_phone, show_location, show_graduation_year}`; phone and
location are on by default, the graduation year (an education entry's dates) is off. It only
changes what a CV header, cover letter or signature shows. Matching, scoring, the verifier and
every other internal reader keep using the stored profile values.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models.settings import AppSetting

KEY = "output_visibility"
DEFAULTS: dict[str, bool] = {"show_phone": True, "show_location": True,
                             "show_graduation_year": False}


def normalize(value: Any) -> dict[str, bool]:
    """A stored value (or nothing) as the flags. A flag that defaults to on stays on unless it is an
    explicit False; a flag that defaults to off is on only when it is an explicit True."""
    raw = value if isinstance(value, dict) else {}
    return {k: (raw.get(k, True) is not False) if default else (raw.get(k) is True)
            for k, default in DEFAULTS.items()}


def load(s: Session) -> dict[str, bool]:
    row = s.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
    return normalize(row.value if row else None)


def check(value: Any) -> None:
    """Validation for PUT /settings/output_visibility (raises ValueError)."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS) \
            or not all(isinstance(v, bool) for v in value.values()):
        raise ValueError("output_visibility takes show_phone, show_location and "
                         "show_graduation_year, each true or false")
