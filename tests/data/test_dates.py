from datetime import date, timedelta

import pytest

from app.data.dates import (
    is_quarter_end,
    most_recent_completed_quarter,
    quarter_end_dates,
)

FIRST_DAY = date(2006, 1, 1)
LAST_DAY = date(2026, 12, 31)
EVERY_DAY = [
    FIRST_DAY + timedelta(days=offset)
    for offset in range((LAST_DAY - FIRST_DAY).days + 1)
]


def test_a_quarter_end_is_a_day_the_quarterly_calendar_lists() -> None:
    calendar = set(quarter_end_dates(FIRST_DAY, LAST_DAY))

    assert [day for day in EVERY_DAY if is_quarter_end(day)] == sorted(calendar)


def test_the_completed_quarter_is_the_last_one_closed_before_todays() -> None:
    for day in EVERY_DAY:
        closed = [end for end in quarter_end_dates(date(2005, 1, 1), day) if end != day]

        assert most_recent_completed_quarter(day) == closed[-1], day


@pytest.mark.parametrize(
    ("as_of", "completed"),
    [
        (date(2026, 1, 1), date(2025, 12, 31)),
        (date(2026, 3, 31), date(2025, 12, 31)),
        (date(2026, 4, 1), date(2026, 3, 31)),
        (date(2026, 8, 9), date(2026, 6, 30)),
        (date(2024, 2, 29), date(2023, 12, 31)),
        (date(2026, 12, 31), date(2026, 9, 30)),
    ],
)
def test_a_quarter_still_running_on_its_last_day_is_not_completed(
    as_of: date, completed: date
) -> None:
    assert most_recent_completed_quarter(as_of) == completed
