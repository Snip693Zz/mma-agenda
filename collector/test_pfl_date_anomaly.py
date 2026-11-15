"""Synthetic tests for offline date anomaly diagnosis."""
import unittest
from pfl_date_anomaly import classify


class DateAnomalyTests(unittest.TestCase):
    def test_chicago_midnight_end_is_classified_without_repair(self):
        result = classify({'startDate': '2026-10-16T23:00:00-04:00', 'endDate': '2026-10-16T00:00:00-04:00'})
        self.assertEqual(result['classification'], 'same_day_midnight_end')
        self.assertEqual(result['status'], 'review_required')
        self.assertFalse(result['date_repair_performed'])
        self.assertFalse(result['automatic_publication'])
        self.assertFalse(result['database_writes'])

    def test_valid_range_is_not_an_anomaly(self):
        result = classify({'startDate': '2026-10-16T23:00:00-04:00', 'endDate': '2026-10-17T00:00:00-04:00'})
        self.assertEqual(result['classification'], 'valid_range')

    def test_other_non_increasing_range_is_not_midnight(self):
        result = classify({'startDate': '2026-10-16T23:00:00-04:00', 'endDate': '2026-10-16T22:00:00-04:00'})
        self.assertEqual(result['classification'], 'other_non_increasing_range')

    def test_invalid_dates_remain_in_review(self):
        result = classify({'startDate': 'not-a-date', 'endDate': '2026-10-16T00:00:00-04:00'})
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'invalid_dates')
