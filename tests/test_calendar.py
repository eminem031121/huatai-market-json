from datetime import date

from market_json.calendar import is_a_share_session


def test_known_session_weekend_and_national_day() -> None:
    assert is_a_share_session(date(2026, 7, 23)) is True
    assert is_a_share_session(date(2026, 7, 25)) is False
    assert is_a_share_session(date(2026, 10, 1)) is False

