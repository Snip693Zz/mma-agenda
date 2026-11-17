"""Synthetic identity regression tests, with no network or database."""
import unittest
from copy import deepcopy
from pfl_reconciliation import extract_event_date, extract_event_identity, reconcile_event

EVENT = dict(id='test', title='PFL Lyon', date='2026-12-19', url='https://pflmma.com/event/test', official=True)
TAIL = '<p>Fight Card</p><p>19 décembre 2026</p><div>Alpha Test vs. Beta Test</div>'
STRUCTURAL_CARD = ('<div id="fight_card_component"><div class="matchupRow">'
                   '<p>Alpha Test vs. Beta Test</p>'
                   '<a href="/fighter/alpha-test">Alpha Test</a>'
                   '<a href="/fighter/beta-test">Beta Test</a>'
                   '</div></div>')


class PrimaryIdentityTests(unittest.TestCase):
    def test_unique_matching_heading(self):
        self.assertTrue(extract_event_identity('<main><h1>PFL <span>Lyon</span></h1>' + TAIL + '</main>', EVENT))

    def test_legacy_fragment_still_supported(self):
        self.assertTrue(extract_event_identity('<h1>  pfl   LYON </h1>' + TAIL, EVENT))

    def test_og_title_identity_without_h1(self):
        html = '<meta property="og:title" content="PFL Lyon">' + TAIL
        self.assertTrue(extract_event_identity(html, EVENT))

    def test_og_title_mismatch_without_h1_blocks(self):
        html = '<meta property="og:title" content="Other Event">' + TAIL
        self.assertFalse(extract_event_identity(html, EVENT))

    def test_og_title_prefix_match_without_h1(self):
        html = '<meta property="og:title" content="PFL">' + TAIL
        self.assertTrue(extract_event_identity(html, EVENT))

    def test_wrong_or_ambiguous_identity_blocks_reconciliation(self):
        cases = [
            ('<header>PFL Lyon</header><main><h1>Other Event</h1>' + TAIL + '</main>', '2026-12-19', 'event_identity_unverified'),
            ('<nav><h1>PFL Lyon</h1></nav>' + TAIL, None, 'missing_or_invalid_date'),
            ('<h1>PFL Lyon</h1><h1>Other Event</h1>' + TAIL, None, 'missing_or_invalid_date'),
            ('<main><h1>PFL Lyon</h1></main><main>' + TAIL + '</main>', None, 'missing_or_invalid_date'),
            ('<h1>PFL Lyon extra</h1>' + TAIL, '2026-12-19', 'event_identity_unverified'),
            ('<main><h1>PFL Lyon</h1>' + TAIL, None, 'missing_or_invalid_date'),
        ]
        for html, expected_date, expected_reason in cases:
            with self.subTest(html=html):
                self.assertFalse(extract_event_identity(html, EVENT))
                self.assertEqual(extract_event_date(html), expected_date)
                existing = [dict(fighter_a='Old A', fighter_b='Old B')]
                original = deepcopy(existing)
                report = reconcile_event(EVENT, existing, html)
                self.assertEqual(report['source_validation']['status'], 'review_required')
                self.assertFalse(report['source_validation']['can_reconcile'])
                self.assertFalse(report['source_validation']['auto_publishable'])
                self.assertEqual(report['source_validation']['reason'], expected_reason)
                self.assertEqual(report['proposals'], [])
                self.assertEqual(existing, original)

    def test_matching_date_in_distinct_primary_block_is_accepted(self):
        html = ('<main><h1>PFL Lyon</h1>'
                '<section><p>19 décembre 2026</p></section>'
                '<section>' + STRUCTURAL_CARD + '</section></main>')
        self.assertTrue(extract_event_identity(html, EVENT))
        self.assertEqual(extract_event_date(html), '2026-12-19')
        report = reconcile_event(EVENT, [], html)
        self.assertEqual(report['source_validation']['status'], 'parsed_candidate')
        self.assertTrue(report['source_validation']['can_reconcile'])
        self.assertEqual(len(report['proposals']), 1)


if __name__ == '__main__':
    unittest.main()
