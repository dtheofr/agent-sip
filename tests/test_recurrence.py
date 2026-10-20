import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from agent_sip.reminders.recurrence import next_occurrence

NY = "America/New_York"
UTC = "UTC"


def ts(year, month, day, hour=0, minute=0, tz=UTC):
    return int(datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz)).timestamp())


def local(epoch, tz):
    return datetime.fromtimestamp(epoch, ZoneInfo(tz))


class RepeatKindsTest(unittest.TestCase):
    def test_none_has_no_next_occurrence(self):
        self.assertIsNone(next_occurrence(ts(2025, 6, 1, 8), "none", UTC))

    def test_daily(self):
        result = next_occurrence(ts(2025, 6, 1, 8, 30), "daily", UTC)
        self.assertEqual(result, ts(2025, 6, 2, 8, 30))

    def test_weekdays_skip_the_weekend(self):
        friday = ts(2025, 6, 6, 8)  # 2025-06-06 is a Friday
        self.assertEqual(local(friday, UTC).weekday(), 4)
        monday = next_occurrence(friday, "weekdays", UTC)
        self.assertEqual(monday, ts(2025, 6, 9, 8))
        self.assertEqual(local(monday, UTC).weekday(), 0)

    def test_weekdays_from_saturday(self):
        saturday = ts(2025, 6, 7, 9)
        self.assertEqual(local(saturday, UTC).weekday(), 5)
        self.assertEqual(next_occurrence(saturday, "weekdays", UTC), ts(2025, 6, 9, 9))

    def test_weekly(self):
        result = next_occurrence(ts(2025, 6, 1, 8), "weekly", UTC)
        self.assertEqual(result, ts(2025, 6, 8, 8))

    def test_monthly(self):
        self.assertEqual(next_occurrence(ts(2025, 6, 15, 8), "monthly", UTC), ts(2025, 7, 15, 8))

    def test_monthly_clamps_to_end_of_month(self):
        self.assertEqual(next_occurrence(ts(2025, 1, 31, 8), "monthly", UTC), ts(2025, 2, 28, 8))

    def test_monthly_clamps_to_leap_day(self):
        self.assertEqual(next_occurrence(ts(2024, 1, 31, 8), "monthly", UTC), ts(2024, 2, 29, 8))

    def test_monthly_december_rolls_over_the_year(self):
        self.assertEqual(next_occurrence(ts(2025, 12, 15, 8), "monthly", UTC), ts(2026, 1, 15, 8))


class DaylightSavingTest(unittest.TestCase):
    def test_daily_keeps_wall_clock_across_spring_forward(self):
        before = ts(2024, 3, 9, 8, tz=NY)  # EST
        after = next_occurrence(before, "daily", NY)
        self.assertEqual(local(after, NY).hour, 8)
        self.assertEqual(local(after, NY).date().isoformat(), "2024-03-10")
        self.assertEqual(after - before, 23 * 3600)  # one hour lost

    def test_daily_keeps_wall_clock_across_fall_back(self):
        before = ts(2024, 11, 2, 8, tz=NY)  # EDT
        after = next_occurrence(before, "daily", NY)
        self.assertEqual(local(after, NY).hour, 8)
        self.assertEqual(local(after, NY).date().isoformat(), "2024-11-03")
        self.assertEqual(after - before, 25 * 3600)  # one hour gained

    def test_weekly_keeps_wall_clock(self):
        before = ts(2024, 3, 3, 8, tz=NY)
        after = next_occurrence(before, "weekly", NY)
        self.assertEqual(local(after, NY).hour, 8)
        self.assertEqual(after - before, 7 * 86400 - 3600)


class UntilAndAnchoringTest(unittest.TestCase):
    def test_until_before_next_stops_the_series(self):
        after = ts(2025, 6, 1, 8)
        self.assertIsNone(next_occurrence(after, "daily", UTC, until=ts(2025, 6, 2, 7, 59)))

    def test_until_is_inclusive(self):
        after = ts(2025, 6, 1, 8)
        self.assertEqual(
            next_occurrence(after, "daily", UTC, until=ts(2025, 6, 2, 8)),
            ts(2025, 6, 2, 8),
        )

    def test_until_after_next_allows_it(self):
        after = ts(2025, 6, 1, 8)
        self.assertEqual(
            next_occurrence(after, "daily", UTC, until=ts(2025, 6, 10)),
            ts(2025, 6, 2, 8),
        )

    def test_after_on_an_occurrence_skips_forward(self):
        occurrence = ts(2025, 6, 1, 8)
        self.assertGreater(next_occurrence(occurrence, "daily", UTC), occurrence)

    def test_past_after_skips_forward(self):
        after = ts(2025, 6, 1, 8)  # "now" is much later; after is in the past
        result = next_occurrence(after, "daily", UTC)
        self.assertGreater(result, after)
        self.assertEqual(result, ts(2025, 6, 2, 8))

    def test_accepts_zoneinfo_instance(self):
        result = next_occurrence(ts(2025, 6, 1, 8, tz=NY), "daily", ZoneInfo(NY))
        self.assertEqual(local(result, NY).hour, 8)

    def test_invalid_repeat_raises(self):
        with self.assertRaises(ValueError):
            next_occurrence(ts(2025, 6, 1, 8), "hourly", UTC)


if __name__ == "__main__":
    unittest.main()
