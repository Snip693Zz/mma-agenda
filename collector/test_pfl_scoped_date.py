"""Synthetic scoped-date regressions; no network or database."""
import unittest
from copy import deepcopy
from pfl_reconciliation import extract_event_date, reconcile_event

EVENT = dict(id='test', title='PFL Lyon', date='2026-12-19', url='https://pflmma.com/event/test', official=True)
CARD = '<p>Fight Card</p><div>Alpha Test vs. Beta Test</div>'


class ScopedDateTests(unittest.TestCase):
    def test_main_date_wins_over_peripheral_dates(self):
        html = '<header>1 janvier 2025</header><main><h1>PFL Lyon</h1><p>19 décembre 2026</p>' + CARD + '</main><footer>2 janvier 2025</footer>'
        self.assertEqual(extract_event_date(html), '2026-12-19')

    def test_repeated_same_date_is_not_ambiguous(self):
        self.assertEqual(extract_event_date('<h1>PFL Lyon</h1><p>19 décembre 2026</p><p>19 décembre 2026</p>'), '2026-12-19')

    def test_unknown_dates_block_and_preserve_existing_fights(self):
        bodies = [
            '<header>19 décembre 2026</header><main><h1>PFL Lyon</h1>' + CARD + '</main>',
            '<main><h1>PFL Lyon</h1><nav>19 décembre 2026</nav>' + CARD + '</main>',
            '<main><h1>PFL Lyon</h1><p>19 décembre 2026</p><p>20 décembre 2026</p>' + CARD + '</main>',
            '<main><h1>PFL Lyon</h1><p>31 février 2026</p>' + CARD + '</main>',
            '<main><h1>PFL Lyon</h1><script>19 décembre 2026</script>' + CARD + '</main>',
            '<main><h1>PFL Lyon</h1><p>19 décembre 2026</p>' + CARD,
            '<main><h1>PFL Lyon</h1><p>19 décembre 2026</p></main><main>' + CARD + '</main>',
        ]
        for html in bodies:
            with self.subTest(html=html):
                self.assertIsNone(extract_event_date(html))
                existing = [dict(fighter_a='Old A', fighter_b='Old B')]
                original = deepcopy(existing)
                result = reconcile_event(EVENT, existing, html)
                self.assertFalse(result['source_validation']['can_reconcile'])
                self.assertEqual(result['source_validation']['reason'], 'missing_or_invalid_date')
                self.assertEqual(result['proposals'], [])
                self.assertEqual(existing, original)
