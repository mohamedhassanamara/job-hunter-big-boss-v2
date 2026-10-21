"""Read-only: today's count by type, the last 14 days of the streak and the chest progress,
for the real workspace, under the current Settings and with emails/LinkedIn counted.

    .venv/bin/python scripts/streak_report.py
"""

from collections import Counter
from datetime import timedelta

from sqlmodel import Session

from app.db import engine
from app.services import motivation as mv
from app.services.motivation import activity, rewards
from app.services.motivation.streak import compute


def show(s: Session, cfg: dict, label: str) -> None:
    today = mv.today(cfg)
    by_type = Counter(kind for at, kind in activity.moments(s, cfg)
                      if mv.local_day(at, cfg) == today)
    counts = activity.per_day(s, cfg)
    st = compute(counts, today, cfg["daily_goal"])
    days = {d.day: d for d in st.calendar}
    chests = rewards.chests(s, cfg)
    print(f"\n== {label}: count_emails={cfg.get('count_emails')} "
          f"count_linkedin={cfg.get('count_linkedin')}")
    print(f"today {today} ({cfg['timezone']}): by type {dict(by_type) or '{}'} -> "
          f"{st.today_count}/{st.goal}, streak {st.current} (longest {st.longest})")
    for i in range(13, -1, -1):
        d = days[today - timedelta(days=i)]
        print(f"  {d.day} {d.day:%a} count={d.count} state={d.state:<12} streak_after={d.streak}")
    print(f"chests: {chests.progress}/{chests.goal} toward the next, {chests.available} waiting, "
          f"{chests.counted} counted since {chests.since}, {chests.opened} opened")


with Session(engine) as session:
    cfg = mv.settings(session)
    show(session, cfg, "current Settings")
    show(session, {**cfg, "count_emails": True, "count_linkedin": True},
         "if emails + LinkedIn counted")
