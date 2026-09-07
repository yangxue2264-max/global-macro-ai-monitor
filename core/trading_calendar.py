from __future__ import annotations

from datetime import date


def is_a_share_trading_day(day: date) -> bool:
    """Use the Shanghai exchange calendar; fail closed to weekday-only if unavailable."""
    try:
        import exchange_calendars as xcals

        return bool(xcals.get_calendar("XSHG").is_session(day.isoformat()))
    except Exception:
        return day.weekday() < 5
