from __future__ import annotations

from datetime import date

import exchange_calendars


def is_a_share_session(day: date) -> bool:
    """Return whether Shanghai/Shenzhen A-share markets trade on *day*."""
    calendar = exchange_calendars.get_calendar("XSHG")
    return bool(calendar.is_session(day.isoformat()))

