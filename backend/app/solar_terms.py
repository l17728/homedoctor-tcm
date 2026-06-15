"""24 Solar Terms (二十四节气) calculator.

Uses a simplified astronomical approximation algorithm based on
the Chinese calendar's solar term calculation. The 24 terms divide
the ecliptic into 24 equal segments of 15° each.

The approximation uses a lookup table of typical dates per term
for the current year, which is accurate to ±1 day — sufficient
for health/wellness advisory purposes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


# 24 solar terms in order, starting from 小寒 (around Jan 6)
# Each entry: (name, month, approximate_day)
# These are approximate fixed dates; real dates vary by ±1 day per year.
# For a health advisory app this precision is sufficient.
SOLAR_TERMS: list[tuple[str, int, int]] = [
    ("小寒", 1, 6),
    ("大寒", 1, 20),
    ("立春", 2, 4),
    ("雨水", 2, 19),
    ("惊蛰", 3, 6),
    ("春分", 3, 21),
    ("清明", 4, 5),
    ("谷雨", 4, 20),
    ("立夏", 5, 6),
    ("小满", 5, 21),
    ("芒种", 6, 6),
    ("夏至", 6, 21),
    ("小暑", 7, 7),
    ("大暑", 7, 23),
    ("立秋", 8, 7),
    ("处暑", 8, 23),
    ("白露", 9, 8),
    ("秋分", 9, 23),
    ("寒露", 10, 8),
    ("霜降", 10, 23),
    ("立冬", 11, 7),
    ("小雪", 11, 22),
    ("大雪", 12, 7),
    ("冬至", 12, 22),
]

# Season mapping for each solar term
TERM_SEASON: dict[str, str] = {
    "小寒": "冬", "大寒": "冬",
    "立春": "春", "雨水": "春", "惊蛰": "春", "春分": "春", "清明": "春", "谷雨": "春",
    "立夏": "夏", "小满": "夏", "芒种": "夏", "夏至": "夏",
    "小暑": "夏", "大暑": "夏",
    "立秋": "秋", "处暑": "秋", "白露": "秋", "秋分": "秋",
    "寒露": "秋", "霜降": "秋",
    "立冬": "冬", "小雪": "冬", "大雪": "冬", "冬至": "冬",
}


def _build_term_dates(year: int) -> list[tuple[str, date]]:
    """Build a sorted list of (term_name, date) for the given year.

    We include the first term of next year to handle late December dates.
    """
    dates: list[tuple[str, date]] = []
    for name, month, day in SOLAR_TERMS:
        try:
            dates.append((name, date(year, month, day)))
        except ValueError:
            pass

    # Add first term of next year for wrap-around
    first_name, first_month, first_day = SOLAR_TERMS[0]
    try:
        dates.append((first_name, date(year + 1, first_month, first_day)))
    except ValueError:
        pass

    dates.sort(key=lambda x: x[1])
    return dates


def get_solar_term(target_date: date | datetime) -> str:
    """Get the current solar term (节气) for the given date.

    Args:
        target_date: The date to look up.

    Returns:
        The name of the solar term that the date falls in.
    """
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    year = target_date.year
    term_dates = _build_term_dates(year)

    # Find which term period the target date falls in
    # Walk backwards through sorted terms; the first term whose date <= target
    for i in range(len(term_dates) - 1, -1, -1):
        if term_dates[i][1] <= target_date:
            return term_dates[i][0]

    # Fallback: should not reach here, but return the last term of prev year
    prev_term_dates = _build_term_dates(year - 1)
    return prev_term_dates[-1][0]


def get_season(term: str) -> str:
    """Get the season (春/夏/秋/冬) for a solar term."""
    return TERM_SEASON.get(term, "未知")


def get_next_term(target_date: date | datetime) -> tuple[str, int]:
    """Get the next solar term and days remaining.

    Returns:
        Tuple of (next_term_name, days_remaining).
    """
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    year = target_date.year
    term_dates = _build_term_dates(year)

    for i, (name, d) in enumerate(term_dates):
        if d > target_date and i + 1 < len(term_dates):
            days_remaining = (d - target_date).days
            return name, days_remaining

    # Wrap to next year
    next_year_dates = _build_term_dates(year + 1)
    if next_year_dates:
        days_remaining = (next_year_dates[0][1] - target_date).days
        return next_year_dates[0][0], days_remaining

    return ("小寒", 0)
