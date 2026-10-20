"""Pure recurrence math for reminders.

``next_occurrence`` is deliberately arithmetic-free of "now": it derives the next
occurrence from the passed ``after`` timestamp, so it is deterministic and easy
to unit-test. Additions are done on the *local wall-clock* datetime in ``tz``
(``zoneinfo``), not on the epoch value, so a reminder set for "every day 08:00"
stays at 08:00 local across DST transitions.

Supported ``repeat`` values: ``none`` (one-shot), ``daily``, ``weekdays``
(Mon-Fri), ``weekly`` and ``monthly``.
"""
from __future__ import annotations

import calendar
import zoneinfo
from datetime import datetime, timedelta

REPEATS = ("none", "daily", "weekdays", "weekly", "monthly")

# Safety bound for the "skip forward until after ``after``" loop. ~27 years of
# daily steps; realistically ``after`` is the previous occurrence or "now".
_MAX_STEPS = 10_000


def _zone(tz: str | zoneinfo.ZoneInfo) -> zoneinfo.ZoneInfo:
    return tz if isinstance(tz, zoneinfo.ZoneInfo) else zoneinfo.ZoneInfo(tz)


def _add_months(moment: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day (Jan 31 + 1 month -> Feb 28/29)."""
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def next_occurrence(
    after: float,
    repeat: str,
    tz: str | zoneinfo.ZoneInfo,
    until: float | None = None,
) -> int | None:
    """Return the first occurrence strictly after ``after``, or ``None``.

    ``after`` and ``until`` are UTC epoch seconds; ``until`` (optional, inclusive)
    caps the series. Returns ``None`` for ``repeat="none"`` (a one-shot has no
    next occurrence) or when the next occurrence would fall after ``until``.

    The local wall-clock time of ``after`` is preserved. If ``after`` already
    lies on an occurrence the next period is returned ("past after skips
    forward"). ``repeat`` not in :data:`REPEATS` raises :class:`ValueError`.

    Note: monthly recurrence anchors on the day-of-month of ``after`` only, so a
    clamped month (Jan 31 -> Feb 28) means the following step is Mar 28, not
    Mar 31. Storing an explicit anchor day is unnecessary for v1.
    """
    if repeat not in REPEATS:
        raise ValueError(f"unknown repeat: {repeat!r}")
    if repeat == "none":
        return None

    moment = datetime.fromtimestamp(after, _zone(tz))
    candidate = moment
    for _ in range(_MAX_STEPS):
        if repeat == "daily":
            candidate = candidate + timedelta(days=1)
        elif repeat == "weekdays":
            candidate = candidate + timedelta(days=1)
            while candidate.weekday() >= 5:  # Saturday/Sunday
                candidate = candidate + timedelta(days=1)
        elif repeat == "weekly":
            candidate = candidate + timedelta(weeks=1)
        else:  # monthly
            candidate = _add_months(candidate, 1)
        timestamp = int(candidate.timestamp())
        if timestamp > after:
            break
    else:  # pragma: no cover - defensive; _MAX_STEPS is far beyond real use
        raise ValueError(f"recurrence {repeat!r} did not advance within {_MAX_STEPS} steps")

    if until is not None and timestamp > until:
        return None
    return timestamp
