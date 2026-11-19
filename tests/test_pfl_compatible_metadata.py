"""Compatibilité du repli HTML, sans réseau ni Supabase."""
import unittest
from collector.pfl_discovery import extract_event_metadata

URL = 'https://pflmma.com/event/test'


class CompatibleMetadataTests(unittest.TestCase):
    def test_original_h1_time_fixture(self):
        result = extract_event_metadata('<h1>Test PFL</h1><time datetime="2026-11-20"></time>', URL)
        self.assertEqual(result['status'], 'metadata_found')
        self.assertEqual(result['date'], '2026-11-20')
        self.assertEqual(result['start_at'], '')

    def test_og_attribute_order(self):
        html = '<meta content="PFL Test" property="og:title"><time datetime="2026-11-20"/>'
        self.assertEqual(extract_event_metadata(html, URL)['title'], 'PFL Test')

    def test_explicit_timezone(self):
        html = '<h1>PFL Test</h1><time datetime="2026-11-20T18:30:00+03:00"></time>'
        self.assertEqual(extract_event_metadata(html, URL)['start_at'], '2026-11-20T18:30:00+03:00')

    def test_no_timezone_no_absolute_start(self):
        html = '<h1>PFL Test</h1><time datetime="2026-11-20T18:30"></time>'
        self.assertEqual(extract_event_metadata(html, URL)['start_at'], '')

    def test_footer_year_not_used(self):
        html = '<h1>PFL Test</h1>FRI NOV 20<footer>2026</footer>'
        self.assertEqual(extract_event_metadata(html, URL)['status'], 'needs_review')

    def test_invalid_date(self):
        html = '<h1>PFL Test</h1><time datetime="2026-02-30"></time>'
        self.assertEqual(extract_event_metadata(html, URL)['reason'], 'fallback_datetime_invalid')

    def test_ambiguous_dates(self):
        html = '<h1>PFL Test</h1><time datetime="2026-11-20"></time><time datetime="2026-11-21"></time>'
        self.assertEqual(extract_event_metadata(html, URL)['status'], 'needs_review')

    def test_scoped_review_cannot_be_bypassed(self):
        html = ('<h2 class="event-info-title">PFL MENA 12</h2>'
                '<h2 class="event-sticky-title">PFL MENA 12 | FRI DEC 11</h2>'
                '<h1>Banner</h1><time datetime="2026-12-11"></time>')
        self.assertEqual(extract_event_metadata(html, URL)['reason'], 'event_year_missing_or_ambiguous')

    def test_empty_scoped_block_cannot_be_bypassed(self):
        html = '<h2 class="event-info-title"></h2><h1>Banner</h1><time datetime="2026-11-20"></time>'
        self.assertEqual(extract_event_metadata(html, URL)['reason'], 'event_title_missing_or_ambiguous')


if __name__ == '__main__':
    unittest.main()
