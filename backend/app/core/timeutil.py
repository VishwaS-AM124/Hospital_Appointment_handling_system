"""Every timezone decision in the system is made here.

Policy: MySQL DATETIME columns hold **naive UTC**. The API speaks timezone-aware
ISO-8601 and refuses ambiguous input. Keeping this in one module is what stops
"off by one timezone" bugs from creeping into the conflict-detection logic.
"""

from datetime import datetime, timezone


def to_utc_naive(dt: datetime) -> datetime:
    """Convert an aware datetime to the naive-UTC form stored in MySQL.

    Raises ValueError on a naive input: guessing the caller's timezone is how
    double-bookings get created across DST boundaries.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("datetime must include a timezone offset")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_now_naive() -> datetime:
    """'Now' in the same shape as the DB columns, for direct comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc_aware(dt: datetime | None) -> datetime | None:
    """Tag a naive-UTC value read from the DB as UTC so it serializes with a 'Z'."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def intervals_overlap(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """True when half-open intervals [a_start, a_end) and [b_start, b_end) intersect.

    Half-open is deliberate: 09:00-09:30 and 09:30-10:00 are back-to-back, not
    overlapping, so a doctor can publish a contiguous run of slots.
    """
    return a_start < b_end and a_end > b_start


def duration_minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)
