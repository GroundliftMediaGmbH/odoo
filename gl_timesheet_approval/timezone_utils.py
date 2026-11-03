# -*- coding: utf-8 -*-
"""GROUNDLIFT attendance display and accounting timezone.

Odoo stores Datetime values as naive UTC.  Neither a website visitor's timezone
nor the employee's individual ``tz`` setting must change the accounting day or
the clock times displayed for the Munich workplace.  pytz's Europe/Berlin zone
contains the historic and future MEZ/MESZ transitions; a fixed +01:00 or +02:00
offset would be wrong for half the year.
"""

from datetime import datetime, time

import pytz


BERLIN_TZ = pytz.timezone("Europe/Berlin")


def utc_aware(value):
    """Interpret an Odoo Datetime (naive UTC) as one unambiguous instant."""
    if value is None or value is False:
        return False
    return pytz.UTC.localize(value) if value.tzinfo is None else value.astimezone(pytz.UTC)


def berlin_datetime(value):
    """Return the same instant in Europe/Berlin, with the correct DST offset."""
    utc_value = utc_aware(value)
    return utc_value.astimezone(BERLIN_TZ) if utc_value else False


def berlin_date(value):
    """Workday is determined by the local *check-in*, not hr.attendance.date."""
    local_value = berlin_datetime(value)
    return local_value.date() if local_value else False


def berlin_zone_label(value):
    """German timezone abbreviation, including the ambiguous autumn hour."""
    local_value = berlin_datetime(value)
    if not local_value:
        return ""
    return "MESZ" if local_value.dst().total_seconds() else "MEZ"


def berlin_month_utc_bounds(month_start):
    """Return [start, end) as naive UTC for a calendar month in Munich.

    Midnight in Berlin is not impacted by the EU 02:00/03:00 DST switch.
    The resulting UTC window is 1h or 2h offset as appropriate for *each*
    boundary, including March and October.
    """
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1, day=1)
    start_local = BERLIN_TZ.localize(datetime.combine(month_start, time.min), is_dst=None)
    end_local = BERLIN_TZ.localize(datetime.combine(next_month, time.min), is_dst=None)
    return (
        start_local.astimezone(pytz.UTC).replace(tzinfo=None),
        end_local.astimezone(pytz.UTC).replace(tzinfo=None),
    )
