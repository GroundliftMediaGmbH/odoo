# -*- coding: utf-8 -*-
"""Timezone regression tests, independent of the current Odoo user's timezone."""

from datetime import date, datetime, timedelta
import unittest

from ..timezone_utils import (
    berlin_date,
    berlin_datetime,
    berlin_month_utc_bounds,
    berlin_zone_label,
)


class TestBerlinTime(unittest.TestCase):
    def test_winter_and_summer(self):
        winter = datetime(2026, 1, 10, 12, 0)
        summer = datetime(2026, 7, 10, 12, 0)
        self.assertEqual(berlin_datetime(winter).hour, 13)
        self.assertEqual(berlin_datetime(summer).hour, 14)
        self.assertEqual(berlin_zone_label(winter), "MEZ")
        self.assertEqual(berlin_zone_label(summer), "MESZ")

    def test_march_spring_forward(self):
        before = datetime(2026, 3, 29, 0, 30)
        after = datetime(2026, 3, 29, 1, 30)
        self.assertEqual(berlin_datetime(before).strftime("%H:%M"), "01:30")
        self.assertEqual(berlin_datetime(after).strftime("%H:%M"), "03:30")
        self.assertEqual(berlin_zone_label(before), "MEZ")
        self.assertEqual(berlin_zone_label(after), "MESZ")
        self.assertEqual((after - before).total_seconds(), 3600)

    def test_october_fall_back(self):
        before = datetime(2026, 10, 25, 0, 30)
        after = datetime(2026, 10, 25, 1, 30)
        self.assertEqual(berlin_datetime(before).strftime("%H:%M"), "02:30")
        self.assertEqual(berlin_datetime(after).strftime("%H:%M"), "02:30")
        self.assertEqual(berlin_zone_label(before), "MESZ")
        self.assertEqual(berlin_zone_label(after), "MEZ")
        self.assertEqual((after - before).total_seconds(), 3600)

    def test_workday_near_midnight_is_berlin_day(self):
        self.assertEqual(berlin_date(datetime(2026, 3, 31, 22, 30)), date(2026, 4, 1))
        self.assertEqual(berlin_date(datetime(2026, 10, 31, 22, 30)), date(2026, 10, 31))
        self.assertEqual(berlin_date(datetime(2026, 10, 31, 23, 30)), date(2026, 11, 1))

    def test_utc_month_boundaries_account_for_dst(self):
        march = berlin_month_utc_bounds(date(2026, 3, 1))
        october = berlin_month_utc_bounds(date(2026, 10, 1))
        self.assertEqual(march, (datetime(2026, 2, 28, 23), datetime(2026, 3, 31, 22)))
        self.assertEqual(october, (datetime(2026, 9, 30, 22), datetime(2026, 10, 31, 23)))
        self.assertEqual(berlin_month_utc_bounds(date(2026, 12, 1))[1], datetime(2026, 12, 31, 23))

    def test_local_midnight_last_and_first_in_month(self):
        start, end = berlin_month_utc_bounds(date(2026, 4, 1))
        self.assertEqual(berlin_date(start), date(2026, 4, 1))
        self.assertEqual(berlin_date(end - timedelta(seconds=1)), date(2026, 4, 30))
        self.assertEqual(berlin_date(end), date(2026, 5, 1))
