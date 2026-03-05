from datetime import datetime

from services.booking_service import msk_str_to_utc, utc_to_msk_str


def test_msk_str_to_utc():
    # Test valid conversion 12:00 MSK should be 09:00 UTC
    dt_utc = msk_str_to_utc("2024-05-15", "12:00")
    assert dt_utc.year == 2024
    assert dt_utc.month == 5
    assert dt_utc.day == 15
    assert dt_utc.hour == 9
    assert dt_utc.minute == 0
    assert dt_utc.tzinfo is None  # Should be naive

def test_utc_to_msk_str():
    # 09:00 UTC should be 12:00 MSK
    dt_utc = datetime(2024, 5, 15, 9, 0)
    msk_str = utc_to_msk_str(dt_utc)
    assert msk_str == "15.05.2024 12:00"
