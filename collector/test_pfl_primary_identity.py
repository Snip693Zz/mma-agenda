"""Synthetic identity regression tests, with no network or database."""
import unittest
from copy import deepcopy
from pfl_reconciliation import extract_event_identity, reconcile_event

EVENT = dict(id='test', title='PFL Lyon', date='2026-12-19', url='https://pflmma.com/event/test', official=True)
TAIL = '<p>Fight Card</p><p>19 décembre 2026</p><div>Alpha Test vs. Beta Test</div>'


class PrimaryIdentityTests(unittest.TestCase):
    def test_unique_matching_heading(self):
        self.assertTrue(extract_event_identity('<main><h1>PFL <span>Lyon</span></h1>' + TAIL + '</main>', EVENT))

    def test_legacy_fragment_still_supported(self):
        self.assertTrue(extract_event_identity('<h1>  pfl   LYON </h1>' + TAIL, EVENT))

    def test_wrong_or_ambiguous_identity_blocks_reconciliation(self):
        cases = [
            '<header>PFL Lyon</header><main><h1>Other Event</h1>' + TAIL + '</main>',
            '<nav><h1>PFL Lyon</h1></nav>' + TAIL,
            '<h1>PFL Lyon</h1><h1>Other Event</h1>' + TAIL,
            '<main><h1>PFL Lyon</h1></main><main>' + TAIL + '</main>',
            '<h1>PFL Lyon extra</h1>' + TAIL,
            '<main><h1>PFL Lyon</h1>' + TAIL,
        ]
        for html in cases:
            with self.subTest(html=html):
                existing = [dict(fighter_a='Old A', fighter_b='Old B')]
                original = deepcopy(existing)
                report = reconcile_event(EVENT, existing, html)
                self.assertFalse(report['source_validation']['can_reconcile'])
                self.assertEqual(report['source_validation']['reason'], 'event_identity_unverified')
                self.assertEqual(report['proposals'], [])
                self.assertEqual(existing, original)
