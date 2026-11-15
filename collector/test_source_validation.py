"""Tests sans dependance externe des controles de source."""
import unittest
from source_validation import assess_source


class SourceValidationTests(unittest.TestCase):
    def check(self, **changes):
        args = dict(expected_date='2026-12-19', observed_date='2026-12-19', identity_verified=True, structured_card=True, fight_count=2)
        args.update(changes)
        return assess_source(**args)

    def test_wrong_year_is_blocked(self):
        self.assertEqual(self.check(observed_date='2025-12-19')['reason'], 'event_date_mismatch')

    def test_missing_or_invalid_dates_are_blocked(self):
        for value in [None, '', '2026-02-30', '2026-12-19T12:00:00Z']:
            with self.subTest(value=value):
                self.assertFalse(self.check(observed_date=value)['can_reconcile'])

    def test_same_date_does_not_prove_identity(self):
        self.assertFalse(self.check(identity_verified=False)['can_reconcile'])

    def test_promotional_text_is_not_a_structured_card(self):
        self.assertFalse(self.check(structured_card=False)['can_reconcile'])

    def test_zero_fights_is_not_a_confirmed_empty_card(self):
        result = self.check(fight_count=0)
        self.assertEqual(result['reason'], 'no_exploitable_fights')
        self.assertFalse(result['empty_card_confirmed'])
        self.assertFalse(result['can_reconcile'])

    def test_invalid_counts_are_blocked(self):
        for count in [-1, True, '2', None]:
            with self.subTest(count=count):
                self.assertFalse(self.check(fight_count=count)['can_reconcile'])

    def test_candidate_does_not_authorize_publication(self):
        result = self.check()
        self.assertTrue(result['can_reconcile'])
        self.assertFalse(result['auto_publishable'])

    def test_defaults_fail_closed(self):
        self.assertFalse(assess_source('2026-12-19', '2026-12-19')['can_reconcile'])
