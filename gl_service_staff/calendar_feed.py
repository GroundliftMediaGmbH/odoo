# -*- coding: utf-8 -*-
"""Private, read-only RFC 5545 subscription feed. Odoo datetime fields are UTC-naive."""
from datetime import datetime


def _escape_ics(value):
    return (str(value or '').replace('\\', '\\\\')
            .replace('\n', '\\n').replace('\r', '')
            .replace(',', '\\,').replace(';', '\\;'))


def _utc_stamp(value):
    if not value:
        return None
    # Odoo datetime columns store naive UTC, never shift these to local time in ICS.
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime('%Y%m%dT%H%M%SZ')


def _fold(text):
    """Fold long iCalendar lines to a max of 75 octets, preserving UTF-8."""
    out, current, count = [], '', 0
    for char in text:
        size = len(char.encode('utf-8'))
        if current and count + size > 75:
            out.append(current)
            current, count = ' ', 1
        current += char
        count += size
    out.append(current)
    return '\r\n'.join(out)


def build_calendar_feed(lines):
    now = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    items = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Groundlift//Servicepersonal//DE',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
        'X-WR-CALNAME:GROUNDLIFT Service-Einsaetze',
        'X-WR-TIMEZONE:Europe/Berlin',
        'REFRESH-INTERVAL;VALUE=DURATION:PT1H',
    ]
    for line in lines:
        start = line.planned_start_datetime or line.shift_id.start_datetime
        end = line.planned_end_datetime or line.shift_id.end_datetime
        if not start or not end or end <= start:
            continue
        modified = line.write_date or line.create_date
        description = 'Fest gebuchter Groundlift-Serviceeinsatz.'
        if line.time_change_state == 'pending':
            description += '\nZeitänderung: Bitte die neue Arbeitszeit bestätigen.'
        items.extend([
            'BEGIN:VEVENT',
            'UID:groundlift-service-shift-line-%s@groundlift.de' % line.id,
            'DTSTAMP:%s' % now,
            'DTSTART:%s' % _utc_stamp(start),
            'DTEND:%s' % _utc_stamp(end),
            'LAST-MODIFIED:%s' % (_utc_stamp(modified) or now),
            'SUMMARY:%s' % _escape_ics('GROUNDLIFT Service – ' + (line.shift_id.name or 'Einsatz')),
            'DESCRIPTION:%s' % _escape_ics(description),
            'STATUS:CONFIRMED',
            'END:VEVENT',
        ])
    items.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in items) + '\r\n'
