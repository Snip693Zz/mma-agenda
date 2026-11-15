"""Regression tests for malformed and timezone-free inputs."""
import unittest
from copy import deepcopy
from pfl_date_anomaly import classify


class RobustnessTests(unittest.TestCase):
    def test_invalid_event_types(self):
        for event in (None, [], 'event', 42, True):
            with self.subTest(event=event):
                self.assertEqual(classify(event)['reason'], 'invalid_event')

    def test_missing_dates(self):
        for event in ({}, {'startDate': None}, {'startDate': '2025-12-13'}):
            with self.subTest(event=event):
                self.assertEqual(classify(event)['reason'], 'missing_dates')

    def test_timezone_required_without_mutation(self):
        for start, end in (
            ('2025-12-13', '2025-12-14'),
            ('2026-10-16T23:00:00', '2026-10-17T00:00:00'),
            ('2026-10-16T23:00:00-04:00', '2026-10-17T00:00:00'),
        ):
            event = {'startDate': start, 'endDate': end}
            original = deepcopy(event)
            with self.subTest(event=event):
                result = classify(event)
                self.assertEqual(result['reason'], 'timezone_required')
                self.assertEqual(result['status'], 'review_required')
                self.assertFalse(result['date_repair_performed'])
                self.assertFalse(result['automatic_publication'])
                self.assertFalse(result['database_writes'])
                self.assertEqual(event, original)
                self.assertEqual(result['startDate'], start)
                self.assertEqual(result['endDate'], end)
