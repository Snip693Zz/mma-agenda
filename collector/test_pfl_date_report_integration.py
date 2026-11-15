"""Offline report integration tests; synthetic evidence, no live capture."""
import json
import unittest
from copy import deepcopy
from pfl_identity_evidence import validate_identity

URL = 'https://pflmma.com/event/2026-chicago2'


class DateReportTests(unittest.TestCase):
    def test_chicago_report_preserves_rejection_and_source(self):
        event = dict(url=URL, name='PFL', startDate='2026-10-16T23:00:00-04:00', endDate='2026-10-16T00:00:00-04:00')
        original = deepcopy(event)
        checked = validate_identity([event], URL)
        report = json.loads(json.dumps({'identity_checks': checked}))
        self.assertEqual(event, original)
        checked = report['identity_checks']
        self.assertEqual(checked['reason'], 'end_not_after_start')
        self.assertEqual(checked['status'], 'review_required')
        self.assertFalse(checked['event_identity_validated'])
        self.assertFalse(checked['automatic_publication'])
        self.assertFalse(checked['database_writes'])
        diagnostic = checked['date_anomaly']
        self.assertEqual(diagnostic['classification'], 'same_day_midnight_end')
        self.assertEqual(diagnostic['status'], 'review_required')
        self.assertFalse(diagnostic['date_repair_performed'])
        self.assertEqual(diagnostic['startDate'], original['startDate'])
        self.assertEqual(diagnostic['endDate'], original['endDate'])

    def test_valid_date_only_remains_candidate_without_anomaly(self):
        event = dict(url=URL, name='PFL', startDate='2025-12-13', endDate='2025-12-14')
        result = validate_identity([event], URL)
        self.assertEqual(result['status'], 'candidate_identity')
        self.assertNotIn('date_anomaly', result)

    def test_wrong_url_does_not_receive_diagnostic(self):
        event = dict(url=URL, name='PFL', startDate='2026-10-16T23:00:00-04:00', endDate='2026-10-16T00:00:00-04:00')
        result = validate_identity([event], 'https://pflmma.com/event/other')
        self.assertEqual(result['reason'], 'jsonld_event_mismatch')
        self.assertNotIn('date_anomaly', result)
