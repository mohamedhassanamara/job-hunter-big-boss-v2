"""Gemini API keys for bulk scoring: a limiter per key and a daily quota per key and model.

- SINGLE-KEY MODE (accounts under review): only the first `gemini.max_keys` keys of .env are used
  (default 1), one request at a time, at most 6 a minute and `gemini.daily_cap` (500) a day over
  every Gemini model, 50 of them kept for work you trigger. The day resets at midnight Pacific.
  No rotation, no bursts. Nothing here ever calls Google by itself: only real requests do.
- Google refusing the key (403 / permission) disables it, PAUSES all Gemini traffic
  (`gemini.paused`) and CV / email generation move to Claude (`model_choice.choice`) until you
  resume.
- When the day's cap is used, `acquire` raises `QuotaWait(resume_at=next midnight Pacific)`: the
  queue pauses and carries on by itself. It never switches model on its own.
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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
# Conservative single-key limits (the accounts are under review): at most 6 requests a minute,
# one at a time, 500 a day across every Gemini model, 50 of them kept for work you trigger.
RPM, TPM, RPD = 6, 250_000, 500
USER_RESERVE = 50  # requests/day that background work (scoring) never uses
MAX_KEYS = 1
DEFAULTS = {"max_keys": MAX_KEYS, "daily_cap": RPD, "paused": False, "paused_reason": None,
            "paused_at": None}
WINDOW = 61.0  # seconds: a little over a minute, so a rolling window never exceeds the limit


def pacific_day(now: datetime | None = None) -> str:
    return (now or utcnow()).astimezone(PACIFIC).strftime("%Y-%m-%d")


def next_reset(now: datetime | None = None) -> datetime:
    """The next midnight Pacific, as an aware UTC datetime."""
    local = (now or utcnow()).astimezone(PACIFIC)
    midnight = datetime(local.year, local.month, local.day, tzinfo=PACIFIC) + timedelta(days=1)
    return midnight.astimezone(UTC)


def configured_keys(max_keys: int | None = None) -> list[tuple[str, str]]:
    """[(label, key)] in .env order: GEMINI_API_KEYS, else GEMINI_API_KEY (also comma-separated),
    cut to the first `max_keys` (setting "Max Gemini keys in use", default 1)."""
    cfg = get_settings()
    raw = cfg.gemini_api_keys or cfg.gemini_api_key
    keys = [(f"key {i}", k.strip()) for i, k in enumerate(raw.split(","), 1) if k.strip()]
    return keys[: max(1, max_keys if max_keys is not None else MAX_KEYS)]


def load_config(engine: Engine) -> dict[str, Any]:
    """The `gemini` app setting over its defaults (max_keys, daily_cap, paused…)."""
    with Session(engine) as s:
        return config(s)


def stored(s: Session) -> dict[str, Any]:
    from app.models import AppSetting

    row = s.exec(select(AppSetting).where(AppSetting.key == "gemini")).first()
    return dict((row.value if row else {}) or {})


def config(s: Session) -> dict[str, Any]:
    return {**DEFAULTS, **stored(s)}


def save_config(s: Session, **changes: Any) -> dict[str, Any]:
    from app.models import AppSetting

    row = s.exec(select(AppSetting).where(AppSetting.key == "gemini")).first()
    value = {**DEFAULTS, **((row.value if row else {}) or {}), **changes}
    if row is None:
        row = AppSetting(key="gemini", value=value)
    else:
        row.value = value
    s.add(row)
    s.commit()
    return value


def is_paused(s: Session) -> bool:
    """True while Gemini is stopped (by you, or because Google refused the key): every Gemini
    request is refused and CV / email generation use Claude."""
    return bool(config(s)["paused"])


def pause(engine: Engine, reason: str) -> None:
    with Session(engine) as s:
        save_config(s, paused=True, paused_reason=reason[:200], paused_at=utcnow().isoformat())
    log.warning("gemini paused: %s", reason[:120])


def resume(engine: Engine) -> None:
    with Session(engine) as s:
        save_config(s, paused=False, paused_reason=None, paused_at=None)


def last4(key: str) -> str:
    return key[-4:]


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:6]


# One request at a time (`KeyPool.one_at_a_time`) and one minute window per key, shared by every
# model's pool: the limits belong to the account, not to the model.
_in_flight = threading.Semaphore(1)
_windows: dict[str, deque[list]] = {}


@dataclass
class Lease:
    label: str
    key: str
    slot: list  # [time, tokens] in the key's minute window; tokens are corrected after the call


class KeyPool:
    """Per-model pool over the configured keys. One instance per (engine, model)."""

    def __init__(self, engine: Engine, model: str, *, rpm: int = RPM, tpm: int = TPM,
                 rpd: int = RPD, user_reserve: int = USER_RESERVE,
                 keys: list[tuple[str, str]] | None = None,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = utcnow):
        self.engine, self.model = engine, model
        self.rpm, self.tpm, self._rpd = rpm, tpm, rpd
        self._user_reserve = user_reserve
        self._user_waiting = 0  # user-priority callers inside acquire(): background yields
        self._keys = keys
        self._clock, self._sleep, self._now = clock, sleep, now
        self._lock = threading.Lock()
        self._windows = _windows

    @property
    def rpd(self) -> int:
        """The daily cap (setting `gemini.daily_cap`), counted over every Gemini model."""
        with Session(self.engine) as s:
            return int(stored(s).get("daily_cap") or self._rpd)

    @property
    def user_reserve(self) -> int:
        return min(self._user_reserve, max(0, self.rpd - 1))

    @property
    def keys(self) -> list[tuple[str, str]]:
        if self._keys is not None:
            return self._keys
        return configured_keys(int(load_config(self.engine)["max_keys"]))

    # database ---------------------------------------------------------------------------------

    def _used_today(self, s: Session, label: str) -> int:
        """Requests today on this key over ALL Gemini models (the cap is per account)."""
        day = pacific_day(self._now())
        rows = s.exec(select(ProviderUsage).where(
            ProviderUsage.key_label == label, ProviderUsage.period == day)).all()
        return sum(r.calls for r in rows if r.provider.startswith(("gemini-", "gemma-")))

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

    def acquire(self, est_tokens: int = 6000, *, priority: str = "user") -> Lease:
        """Reserve one request on the (single) key; waits for the minute window. Raises QuotaWait
        when Gemini is paused, the key is refused, or today's cap is used.
        Wrap acquire + the HTTP call in `one_at_a_time()` (concurrency 1).

        `priority`: "user" is work you triggered (a CV, an email, a click); "background" is bulk
        scoring. Background yields while any user call waits, and never uses the last
        `user_reserve` requests of the day."""
        background = priority == "background"
        if not background:
            with self._lock:
                self._user_waiting += 1
        try:
            while background and self._user_waiting > 0:
                self._sleep(0.5)  # user work goes first
            return self._acquire(est_tokens, background)
        finally:
            if not background:
                with self._lock:
                    self._user_waiting -= 1

    @contextmanager
    def one_at_a_time(self) -> Iterator[None]:
        """Concurrency 1 over every Gemini model: the next request starts when this one is done."""
        with _in_flight:
            yield

    def _acquire(self, est_tokens: int, background: bool) -> Lease:
        while True:
            wait = 0.0
            cap = self.rpd
            limit = cap - (self.user_reserve if background else 0)
            with self._lock, Session(self.engine) as s:
                if is_paused(s):
                    reason = config(s)["paused_reason"] or "paused"
                    raise QuotaWait(f"Gemini is paused ({reason}). Settings → Models.", None)
                usable = None
                exhausted = disabled = 0
                for label, key in self.keys:
                    st = self._state(s, label)
                    if st is not None and st.disabled_at is not None:
                        disabled += 1
                        continue
                    usage = self._usage(s, label)
                    if self._used_today(s, label) >= limit:
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
                window = self._windows.setdefault(f"{id(self.engine)}:{label}", deque())
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
            usage.calls += max(0, self.rpd - self._used_today(s, lease.label))
            s.add(usage)
            s.commit()
        log.warning("gemini %s (…%s) is out of quota for today", lease.label, last4(lease.key))

    def disable(self, lease: Lease, reason: str) -> None:
        """Google refuses this key (403 / permission): disable it at once, stop ALL Gemini traffic
        (the pause switch) so CV and email generation move to Claude, until you resume."""
        with self._lock, Session(self.engine) as s:
            st = self._state(s, lease.label)
            if st is None:
                st = ProviderKeyState(provider=PROVIDER, key_label=lease.label)
            st.disabled_at, st.disabled_reason = utcnow(), reason[:200]
            s.add(st)
            s.commit()
        log.warning("gemini %s (…%s) disabled: %s", lease.label, last4(lease.key), reason[:120])
        pause(self.engine, f"Google refused {lease.label} (…{last4(lease.key)}): {reason}")

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
                disabled = st is not None and st.disabled_at is not None
                used = self._used_today(s, label)
                state = "disabled" if disabled else "exhausted" if used >= self.rpd else "ok"
                window = self._windows.get(f"{id(self.engine)}:{label}", deque())
                recent = sum(1 for w in window if self._clock() - w[0] < WINDOW)
                out.append({"label": label, "fingerprint": fingerprint(key), "last4": last4(key),
                            "used": used,
                            "limit": self.rpd, "remaining": max(0, self.rpd - used), "state": state,
                            "reason": st.disabled_reason if disabled and st else None,
                            "last_minute": recent})
            cfg = config(s)
            s.commit()
        live = [k for k in out if k["state"] != "disabled"]
        remaining = sum(k["remaining"] for k in live)
        pooled = {"used": sum(k["used"] for k in live), "limit": self.rpd * len(live),
                  "remaining": remaining, "keys": len(live), "user_reserve": self.user_reserve}
        return {"model": self.model, "keys": out, "limits": {"rpm": self.rpm, "tpm": self.tpm,
                                                              "rpd": self.rpd},
                "pooled": pooled, "paused": bool(cfg["paused"]),
                "paused_reason": cfg["paused_reason"], "max_keys": int(cfg["max_keys"]),
                "reserve": self.user_reserve,
                "remaining_today": remaining, "day": pacific_day(now),
                "resets_at": next_reset(now).isoformat()}


_pools: dict[tuple[int, str], KeyPool] = {}
_pools_lock = threading.Lock()


def pool_for(engine: Engine, model: str) -> KeyPool:
    with _pools_lock:
        pool = _pools.get((id(engine), model))
        if pool is None:
            pool = KeyPool(engine, model)  # the same conservative limits for every model
            _pools[(id(engine), model)] = pool
        return pool
