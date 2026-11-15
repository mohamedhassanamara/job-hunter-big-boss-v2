"""The workday streak: a pure function of the counts per day (never stored, so it can't drift).

- A workday (Mon-Fri) counts when you reach the daily goal; a missed workday resets the streak
  to 0 (from the next day). Today is "in progress" until midnight in your timezone: never shown
  as broken before the day ends.
- Saturday and Sunday count by themselves, but only while a streak is running: they carry a
  streak, they never start or revive one.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKS = 8  # the calendar on Today


@dataclass
class Day:
    day: date
    count: int
    state: str  # met | freeze | missed | in_progress | weekend | weekend_idle | idle | future
    streak: int  # the streak at the end of that day


@dataclass
class Streak:
    current: int
    longest: int
    today_count: int
    goal: int
    today_state: str  # met | freeze | in_progress | weekend | weekend_idle
    calendar: list[Day] = field(default_factory=list)


def compute(counts: Mapping[date, int], today: date, goal: int, weeks: int = WEEKS,
            frozen: Collection[date] = ()) -> Streak:
    goal = max(1, int(goal))
    frozen = {f for f in frozen if f.weekday() < 5}  # a freeze only ever covers a workday
    first = min([d for d, n in counts.items() if n > 0] + list(frozen), default=today)
    days: dict[date, Day] = {}
    streak = longest = 0
    d = min(first, today)
    while d <= today:
        n = counts.get(d, 0)
        if d.weekday() < 5:
            if n >= goal:  # a frozen day that also reaches the goal counts once, as "met"
                streak += 1
                state = "met"
            elif d in frozen:
                streak += 1
                state = "freeze"
            elif d == today:
                state = "in_progress"  # until midnight: the streak shown is yesterday's
            else:
                streak, state = 0, "missed"
        elif streak > 0:
            streak += 1
            state = "weekend"
        else:
            state = "weekend_idle"
        longest = max(longest, streak)
        days[d] = Day(d, n, state, streak)
        d += timedelta(days=1)
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    calendar = []
    for i in range(weeks * 7):
        day = start + timedelta(days=i)
        if day > today:
            calendar.append(Day(day, 0, "future", 0))
        else:
            calendar.append(days.get(day) or Day(day, 0, "idle", 0))
    return Streak(current=streak, longest=longest, today_count=counts.get(today, 0), goal=goal,
                  today_state=days[today].state, calendar=calendar)
