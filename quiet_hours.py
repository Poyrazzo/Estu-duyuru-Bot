from datetime import datetime, time


def _parse_time(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


def is_quiet_now(start: str, end: str) -> bool:
    """Return True if current local time is within quiet hours [start, end)."""
    now = datetime.now().time().replace(second=0, microsecond=0)
    start_t = _parse_time(start)
    end_t = _parse_time(end)

    if start_t <= end_t:
        # e.g. 09:00 – 17:00 (same day)
        return start_t <= now < end_t
    else:
        # Overnight: e.g. 23:00 – 07:00
        return now >= start_t or now < end_t
