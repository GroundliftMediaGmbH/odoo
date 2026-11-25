# -*- coding: utf-8 -*-
"""Standalone tests: python -m unittest discover -s tests -p 'test_*.py' -v

These helpers are deliberately Odoo-independent, so the civil-time edge cases
can be checked before deploying to an Odoo.sh staging environment.
"""
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import unittest

import pytz


MODULE = Path(__file__).resolve().parents[1] / "hours_timezone.py"
spec = importlib.util.spec_from_file_location("gl_hours_timezone_under_test", MODULE)
tzutils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tzutils)

BERLIN = tzutils.PORTAL_TZ
UTC = pytz.UTC


def utc(y, m, d, h=0, minute=0):
    return UTC.localize(datetime(y, m, d, h, minute))


def local(y, m, d, h=0, minute=0):
    return BERLIN.localize(datetime(y, m, d, h, minute), is_dst=None)


class BerlinTimeTests(unittest.TestCase):
    def test_utc_to_berlin_is_one_hour_in_winter_two_in_summer(self):
        self.assertEqual(tzutils.as_utc(datetime(2026, 1, 15, 8)).astimezone(BERLIN), local(2026, 1, 15, 9))
        self.assertEqual(tzutils.as_utc(datetime(2026, 7, 15, 8)).astimezone(BERLIN), local(2026, 7, 15, 10))

    def test_march_month_end_has_different_offset_than_month_start(self):
        start_local, end_local, start_utc, end_utc = tzutils.month_bounds(2026, 3)
        self.assertEqual(start_local.utcoffset(), timedelta(hours=1))
        self.assertEqual(end_local.utcoffset(), timedelta(hours=2))
        self.assertEqual(start_utc, datetime(2026, 2, 28, 23))
        self.assertEqual(end_utc, datetime(2026, 3, 31, 22))

    def test_october_month_end_has_different_offset_than_month_start(self):
        start_local, end_local, start_utc, end_utc = tzutils.month_bounds(2026, 10)
        self.assertEqual(start_local.utcoffset(), timedelta(hours=2))
        self.assertEqual(end_local.utcoffset(), timedelta(hours=1))
        self.assertEqual(start_utc, datetime(2026, 9, 30, 22))
        self.assertEqual(end_utc, datetime(2026, 10, 31, 23))

    def test_spring_change_23_hour_day(self):
        begin = local(2026, 3, 29).astimezone(UTC)
        finish = local(2026, 3, 30).astimezone(UTC)
        ms, me = utc(2026, 3, 1), utc(2026, 4, 1)
        segments = list(tzutils.split_utc_by_local_day(begin, finish, ms, me))
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0][1] - segments[0][0]).total_seconds() / 3600, 23)
        self.assertEqual(segments[0][0].astimezone(BERLIN).strftime('%H:%M %Z'), '00:00 CET')
        self.assertEqual(segments[0][1].astimezone(BERLIN).strftime('%H:%M %Z'), '00:00 CEST')

    def test_autumn_change_25_hour_day(self):
        begin = local(2026, 10, 25).astimezone(UTC)
        finish = local(2026, 10, 26).astimezone(UTC)
        ms, me = utc(2026, 10, 1), utc(2026, 11, 1)
        segments = list(tzutils.split_utc_by_local_day(begin, finish, ms, me))
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0][1] - segments[0][0]).total_seconds() / 3600, 25)

    def test_spring_short_shift_real_duration_and_labels(self):
        # 01:30 MEZ -> 03:30 MESZ is 1h of real work, not 2h.
        begin, finish = utc(2026, 3, 29, 0, 30), utc(2026, 3, 29, 1, 30)
        segs = list(tzutils.split_utc_by_local_day(begin, finish, utc(2026, 2, 28), utc(2026, 4, 1)))
        self.assertEqual(len(segs), 1)
        a, b = segs[0]
        self.assertEqual(tzutils.local_clock_label(a.astimezone(BERLIN), True), '01:30 MEZ')
        self.assertEqual(tzutils.local_clock_label(b.astimezone(BERLIN), True), '03:30 MESZ')
        self.assertEqual((b - a).total_seconds(), 3600)

    def test_autumn_repeated_two_oclock(self):
        # 02:30 MESZ -> 02:30 MEZ is a full hour of actual work.
        a, b = utc(2026, 10, 25, 0, 30), utc(2026, 10, 25, 1, 30)
        self.assertEqual(tzutils.local_clock_label(a.astimezone(BERLIN), True), '02:30 MESZ')
        self.assertEqual(tzutils.local_clock_label(b.astimezone(BERLIN), True), '02:30 MEZ')
        self.assertEqual((b - a).total_seconds(), 3600)

    def test_cross_midnight_in_summer(self):
        begin, finish = utc(2026, 7, 10, 21, 30), utc(2026, 7, 11, 1, 0)
        segs = list(tzutils.split_utc_by_local_day(begin, finish, utc(2026, 6, 30), utc(2026, 7, 31)))
        self.assertEqual([int((b-a).total_seconds()/60) for a,b in segs], [30, 180])
        self.assertEqual([a.astimezone(BERLIN).date().isoformat() for a,b in segs], ['2026-07-10','2026-07-11'])

    def test_exact_month_boundary_not_double_counted(self):
        begin, finish = utc(2026, 3, 31, 21, 30), utc(2026, 3, 31, 22, 30)
        ms, me, *_ = tzutils.month_bounds(2026, 3)
        aprs, apre, *_ = tzutils.month_bounds(2026, 4)
        march = list(tzutils.split_utc_by_local_day(begin, finish, ms.astimezone(UTC), me.astimezone(UTC)))
        april = list(tzutils.split_utc_by_local_day(begin, finish, aprs.astimezone(UTC), apre.astimezone(UTC)))
        self.assertEqual([int((b-a).total_seconds()/60) for a,b in march], [30])
        self.assertEqual([int((b-a).total_seconds()/60) for a,b in april], [30])
        self.assertEqual(april[0][0].astimezone(BERLIN).strftime('%d.%m %H:%M'), '01.04 00:00')

    def test_december_to_january(self):
        _, end, _, utc_end = tzutils.month_bounds(2026, 12)
        self.assertEqual(end, local(2027, 1, 1))
        self.assertEqual(utc_end, datetime(2026, 12, 31, 23))


if __name__ == '__main__':
    unittest.main()
