"""Gemini API keys for bulk scoring: a limiter per key and a daily quota per key and model.

- Free-tier limits per key (separate Google projects have separate quotas): 15 requests/minute,
  250K input tokens/minute, 500 requests/day. The day resets at midnight Pacific time.
- Keys are used IN ORDER: key 1 until its daily quota is used, then key 2. Within a key, calls wait
  for the minute window (they never spill to the next key just because of the per-minute limit).
- When every usable key is out of quota, `acquire` raises `QuotaWait(resume_at=next midnight
  Pacific)`: the queue pauses and carries on by itself. It never switches model on its own.
- A key Google refuses (invalid, suspended, leaked) is disabled with a warning and never retried
  until you enable it again. A key Google says is out of daily quota is parked until the reset.
- Usage is stored per (key label, model, Pacific date) in `provider_usage`, so a restart never
  resets the count; the disabled state is `provider_key_state`. Keys are only ever referred to by
  label ("key 1") and a short fingerprint, never stored or logged.
"""

import hashlib
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.config import get_settings
from app.models import ProviderKeyState, ProviderUsage
from app.models.base import utcnow
from app.providers.base import QuotaWait

log = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
PROVIDER = "gemini"  # provider_key_state: a refused key is refused for every model
RPM, TPM, RPD = 15, 250_000, 500
WINDOW = 61.0  # seconds: a little over a minute, so a rolling window never exceeds the limit


def pacific_day(now: datetime | None = None) -> str:
    return (now or utcnow()).astimezone(PACIFIC).strftime("%Y-%m-%d")


def next_reset(now: datetime | None = None) -> datetime:
    """The next midnight Pacific, as an aware UTC datetime."""
    local = (now or utcnow()).astimezone(PACIFIC)
    midnight = datetime(local.year, local.month, local.day, tzinfo=PACIFIC) + timedelta(days=1)
    return midnight.astimezone(UTC)


def configured_keys() -> list[tuple[str, str]]:
    """[(label, key)] in .env order: GEMINI_API_KEYS, else GEMINI_API_KEY (also comma-separated)."""
    cfg = get_settings()
    raw = cfg.gemini_api_keys or cfg.gemini_api_key
    return [(f"key {i}", k.strip()) for i, k in enumerate(raw.split(","), 1) if k.strip()]


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:6]


@dataclass
class Lease:
    label: str
    key: str
    slot: list  # [time, tokens] in the key's minute window; tokens are corrected after the call


class KeyPool:
    """Per-model pool over the configured keys. One instance per (engine, model)."""

    def __init__(self, engine: Engine, model: str, *, rpm: int = RPM, tpm: int = TPM,
                 rpd: int = RPD, keys: list[tuple[str, str]] | None = None,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = utcnow):
        self.engine, self.model = engine, model
        self.rpm, self.tpm, self.rpd = rpm, tpm, rpd
        self._keys = keys
        self._clock, self._sleep, self._now = clock, sleep, now
        self._lock = threading.Lock()
        self._windows: dict[str, deque[list]] = {}

    @property
    def keys(self) -> list[tuple[str, str]]:
        return self._keys if self._keys is not None else configured_keys()

    # database ---------------------------------------------------------------------------------

    def _usage(self, s: Session, label: str) -> ProviderUsage:
        day = pacific_day(self._now())
        row = s.exec(select(ProviderUsage).where(
            ProviderUsage.provider == self.model, ProviderUsage.key_label == label,
            ProviderUsage.period == day)).first()
        if row is None:
            row = ProviderUsage(provider=self.model, key_label=label, period=day)
            s.add(row)
            s.flush()
        return row

    @staticmethod
    def _state(s: Session, label: str) -> ProviderKeyState | None:
        return s.exec(select(ProviderKeyState).where(
            ProviderKeyState.provider == PROVIDER, ProviderKeyState.key_label == label)).first()

    # acquire / report -------------------------------------------------------------------------

    def acquire(self, est_tokens: int = 6000) -> Lease:
        """Reserve one request on the first usable key; waits for its minute window. Raises
        QuotaWait when no key can take a request until the daily reset (or ever, if all refused)."""
        while True:
            wait = 0.0
            with self._lock, Session(self.engine) as s:
                usable = None
                exhausted = disabled = 0
                for label, key in self.keys:
                    st = self._state(s, label)
                    if st is not None and st.disabled_at is not None:
                        disabled += 1
                        continue
                    usage = self._usage(s, label)
                    if usage.calls >= self.rpd:
                        exhausted += 1
                        continue
                    usable = (label, key, usage)
                    break
                if usable is None:
                    s.commit()
                    if exhausted:
                        reset = next_reset(self._now())
                        raise QuotaWait(
                            f"Today's Gemini quota is used up on {exhausted} key(s)"
                            + (f" ({disabled} disabled)" if disabled else "") + ".", reset)
                    if disabled:
                        raise QuotaWait("Every Gemini API key was refused or disabled "
                                        "(Settings → Models).", None)
                    raise QuotaWait("No Gemini API key configured (GEMINI_API_KEYS in .env).", None)
                label, key, usage = usable
                now = self._clock()
                window = self._windows.setdefault(label, deque())
                while window and now - window[0][0] >= WINDOW:
                    window.popleft()
                tokens = sum(w[1] for w in window)
                if len(window) < self.rpm and tokens + est_tokens <= self.tpm * 0.9:
                    slot = [now, est_tokens]
                    window.append(slot)
                    usage.calls += 1
                    s.add(usage)
                    s.commit()
                    return Lease(label, key, slot)
                wait = max(0.2, WINDOW - (now - window[0][0])) if window else 0.2
            self._sleep(min(wait, 5.0))

    def report(self, lease: Lease, input_tokens: int | None) -> None:
        """Correct the minute window's token count with the real one."""
        if input_tokens:
            lease.slot[1] = input_tokens

    def mark_exhausted(self, lease: Lease) -> None:
        """Google says this key's daily quota is used up (our own count was lower)."""
        with self._lock, Session(self.engine) as s:
            usage = self._usage(s, lease.label)
            usage.calls = max(usage.calls, self.rpd)
            s.add(usage)
            s.commit()
        log.warning("gemini %s (%s) is out of quota for today; moving on", lease.label,
                    fingerprint(lease.key))

    def disable(self, lease: Lease, reason: str) -> None:
        """Google refuses this key: never use it again until the user enables it."""
        with self._lock, Session(self.engine) as s:
            st = self._state(s, lease.label)
            if st is None:
                st = ProviderKeyState(provider=PROVIDER, key_label=lease.label)
            st.disabled_at, st.disabled_reason = utcnow(), reason[:200]
            s.add(st)
            s.commit()
        log.warning("gemini %s (%s) disabled: %s", lease.label, fingerprint(lease.key),
                    reason[:120])

    def enable(self, label: str) -> bool:
        with self._lock, Session(self.engine) as s:
            st = self._state(s, label)
            if st is None:
                return False
            st.disabled_at = st.disabled_reason = None
            s.add(st)
            s.commit()
            return True

    # read side --------------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """For Settings → Models and Today: remaining quota per key (this app's count; Google's
        own page is the source of truth, e.g. when other tools use the same key)."""
        now = self._now()
        out = []
        with self._lock, Session(self.engine) as s:
            for label, key in self.keys:
                st = self._state(s, label)
                usage = self._usage(s, label)
                disabled = st is not None and st.disabled_at is not None
                used = usage.calls
                state = "disabled" if disabled else "exhausted" if used >= self.rpd else "ok"
                window = self._windows.get(label, deque())
                recent = sum(1 for w in window if self._clock() - w[0] < WINDOW)
                out.append({"label": label, "fingerprint": fingerprint(key), "used": used,
                            "limit": self.rpd, "remaining": max(0, self.rpd - used), "state": state,
                            "reason": st.disabled_reason if disabled and st else None,
                            "last_minute": recent})
            s.commit()
        remaining = sum(k["remaining"] for k in out if k["state"] != "disabled")
        return {"model": self.model, "keys": out, "limits": {"rpm": self.rpm, "tpm": self.tpm,
                                                              "rpd": self.rpd},
                "remaining_today": remaining, "day": pacific_day(now),
                "resets_at": next_reset(now).isoformat()}


_pools: dict[tuple[int, str], KeyPool] = {}
_pools_lock = threading.Lock()


def pool_for(engine: Engine, model: str) -> KeyPool:
    with _pools_lock:
        pool = _pools.get((id(engine), model))
        if pool is None:
            pool = KeyPool(engine, model)
            _pools[(id(engine), model)] = pool
        return pool
