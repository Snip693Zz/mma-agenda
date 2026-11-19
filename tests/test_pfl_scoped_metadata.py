"""Tests des sélecteurs PFL et de l'ordre de visite."""
import unittest
from collector.pfl_discovery import extract_event_links, extract_event_metadata
from collector.pfl_scoped_metadata import extract_scoped_metadata

URL = 'https://pflmma.com/event/pfl-test-2026'

def page(date='SAT DEC 19', title='PFL Test'):
    return ('<h3>PFL Lyon</h3><h2 class="event-info-title text-uppercase">'
            + title + '</h2><h2 class="event-sticky-title">'
            + title + ' | ' + date + '</h2><footer>2030</footer>')

class ScopedMetadataTests(unittest.TestCase):
    def test_listing_order_and_deduplication(self):
        html = ''.join('<a href="/event/' + slug + '">x</a>' for slug in (
            'pfl-test-2026', '2018-pfl-1', 'pfl-test-2026', 'pflmena-12'))
        self.assertEqual(extract_event_links(html, 'https://pflmma.com/events'), [
            URL, 'https://pflmma.com/event/2018-pfl-1', 'https://pflmma.com/event/pflmena-12'])

    def test_scoped_title_not_banner(self):
        result = extract_scoped_metadata(page(), URL)
        self.assertEqual(result['title'], 'PFL Test')
        self.assertEqual(result['date'], '2026-12-19')
        self.assertEqual(result['start_at'], '')

    def test_year_not_inferred_from_footer(self):
        result = extract_scoped_metadata(page(), 'https://pflmma.com/event/pflmena-12')
        self.assertEqual(result['reason'], 'event_year_missing_or_ambiguous')

    def test_explicit_year(self):
        result = extract_scoped_metadata(page('SAT DEC 19 2026'), 'https://pflmma.com/event/test')
        self.assertEqual(result['date'], '2026-12-19')

    def test_year_conflict(self):
        result = extract_scoped_metadata(page('SAT DEC 19 2027'), URL)
        self.assertEqual(result['reason'], 'event_year_missing_or_ambiguous')

    def test_weekday_mismatch(self):
        self.assertEqual(extract_scoped_metadata(page('FRI DEC 19'), URL)['reason'], 'event_weekday_mismatch')

    def test_invalid_date(self):
        self.assertEqual(extract_scoped_metadata(page('FEB 30'), URL)['reason'], 'event_date_invalid')

    def test_wrong_event_date_rejected(self):
        html = '<h2 class="event-info-title">PFL Test</h2><h2 class="event-sticky-title">PFL Lyon | SAT DEC 19</h2>'
        self.assertEqual(extract_scoped_metadata(html, URL)['reason'], 'event_date_missing_or_ambiguous')

    def test_fallback_integration(self):
        self.assertEqual(extract_event_metadata(page(), URL)['date'], '2026-12-19')

if __name__ == '__main__':
    unittest.main()
