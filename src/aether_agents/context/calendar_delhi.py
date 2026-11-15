"""Festival and public-holiday hooks for Delhi winter (Oct–Mar).

Dates are approximate Gregorian anchors for deterministic v1 scoring.
Lunar festivals (Diwali, Holi) use known winter-season windows used in
case-study literature; ingest/eval can override via extras later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class CalendarHit:
    name: str
    kind: str  # festival | holiday
    date: date


# Fixed civil holidays relevant to Delhi winter / post-monsoon period.
_FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 26, "Republic Day"),
    (10, 2, "Gandhi Jayanti"),
    (12, 25, "Christmas"),
)

# Approximate festival windows (month, day); midpoints for Diwali/Holi vary yearly.
# These are hooks for feature flags, not liturgical authority.
_FESTIVAL_WINDOWS: tuple[tuple[int, int, int, str], ...] = (
    # (month, start_day, end_day, name)
    (10, 20, 31, "Diwali window"),
    (11, 1, 5, "Diwali window"),
    (11, 12, 16, "Guru Nanak Jayanti window"),
    (1, 13, 14, "Lohri / Makar Sankranti"),
    (3, 5, 20, "Holi window"),
)

_WINTER_MONTHS = {10, 11, 12, 1, 2, 3}


class DelhiCalendar:
    """Deterministic calendar feature hooks for Delhi–NCT winter episodes."""

    def is_winter_season(self, when: date | datetime) -> bool:
        d = when.date() if isinstance(when, datetime) else when
        return d.month in _WINTER_MONTHS

    def lookup(self, when: date | datetime) -> list[CalendarHit]:
        d = when.date() if isinstance(when, datetime) else when
        hits: list[CalendarHit] = []
        for month, day, name in _FIXED_HOLIDAYS:
            if d.month == month and d.day == day:
                hits.append(CalendarHit(name=name, kind="holiday", date=d))
        for month, start_day, end_day, name in _FESTIVAL_WINDOWS:
            if d.month == month and start_day <= d.day <= end_day:
                hits.append(CalendarHit(name=name, kind="festival", date=d))
        return hits

    def features(self, when: date | datetime) -> dict[str, object]:
        hits = self.lookup(when)
        festival = next((h for h in hits if h.kind == "festival"), None)
        holiday = next((h for h in hits if h.kind == "holiday"), None)
        return {
            "is_delhi_winter_season": self.is_winter_season(when),
            "is_festival": festival is not None,
            "festival_name": festival.name if festival else None,
            "is_holiday": holiday is not None,
            "holiday_name": holiday.name if holiday else None,
        }
