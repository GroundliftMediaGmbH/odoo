# -*- coding: utf-8 -*-
"""Timezone-safe helpers for hr.attendance, whose datetimes are UTC in Odoo.

All interval arithmetic happens with UTC-aware datetimes. Calendar boundaries
are created separately as *local* midnights, so pytz never retains a stale
CET/CEST offset across a daylight-saving transition.
"""
from datetime import datetime, time, timedelta

import pytz


PORTAL_TZ = pytz.timezone("Europe/Berlin")
UTC = pytz.UTC


def as_utc(value):
    """Treat naive Odoo Datetime values as UTC (never as server-local time)."""
    if value.tzinfo is None:
        return UTC.localize(value)
    return value.astimezone(UTC)


def local_midnight(day, tz=PORTAL_TZ):
    """Construct the real midnight for this civil day, with its own offset."""
    return tz.localize(datetime.combine(day, time.min), is_dst=None)


def month_bounds(year, month, tz=PORTAL_TZ):
    """Return (start_local, end_local, start_naive_utc, end_naive_utc).

    The UTC bounds are suitable for Odoo ORM domains; the local bounds are
    suitable for comparisons/display. Both are half-open: [start, end).
    """
    month_start = datetime(year, month, 1).date()
    if month == 12:
        following = datetime(year + 1, 1, 1).date()
    else:
        following = datetime(year, month + 1, 1).date()

    start_local = local_midnight(month_start, tz)
    end_local = local_midnight(following, tz)
    start_utc = start_local.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_local.astimezone(UTC).replace(tzinfo=None)
    return start_local, end_local, start_utc, end_utc


def split_utc_by_local_day(start_utc, end_utc, month_start_utc, month_end_utc, tz=PORTAL_TZ):
    """Yield real elapsed UTC intervals, cut at each Europe/Berlin midnight.

    Arguments are timezone-aware UTC instants. On DST changes local days can
    contain 23 or 25 real hours; they are never assumed to be 24 hours long.
    """
    cursor = max(as_utc(start_utc), as_utc(month_start_utc))
    finish = min(as_utc(end_utc), as_utc(month_end_utc))
    while cursor < finish:
        current_local_day = cursor.astimezone(tz).date()
        next_local_day = current_local_day + timedelta(days=1)
        next_midnight_utc = local_midnight(next_local_day, tz).astimezone(UTC)
        segment_end = min(next_midnight_utc, finish)
        yield cursor, segment_end
        cursor = segment_end


def local_clock_label(value, show_offset=False):
    """Human-readable German clock time; label the two sides of a DST switch."""
    label = value.strftime("%H:%M")
    if show_offset:
        label += " MESZ" if value.dst() else " MEZ"
    return label
