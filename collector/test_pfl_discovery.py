"""Tests hors ligne de la découverte PFL : aucun réseau, aucune écriture."""
import json
import unittest
from pfl_discovery import build_discovery_report, extract_event_links, extract_event_metadata

LISTING_URL = 'https://pflmma.com/events'
EVENT_URL = 'https://pflmma.com/event/pfl-lyon'
TODAY = '2026-11-16'


def listing(*slugs):
    links = ''.join(f'<a href="/event/{slug}">Event</a>' for slug in slugs)
    return f'<html><body>{links}</body></html>'


def event_page(url, title='PFL Lyon', date='2026-12-11'):
    payload = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': title,
        'startDate': date,
        'url': url,
        'location': {'name': 'Lyon, France'},
    }
    return f'<html><script type="application/ld+json">{json.dumps(payload)}</script></html>'


class DiscoveryTests(unittest.TestCase):
    def test_event_links_are_canonical_deduplicated_and_in_listing_order(self):
        html = listing('pfl-lyon', 'pfl-lyon', '2026-chicago2')
        html += '<a href="https://www.pflmma.com/event/pfl-lyon/">Duplicate</a>'
        links = extract_event_links(html, LISTING_URL)
        self.assertEqual(links, [
            'https://pflmma.com/event/pfl-lyon',
            'https://pflmma.com/event/2026-chicago2',
        ])

    def test_metadata_is_extracted_from_matching_jsonld(self):
        metadata = extract_event_metadata(event_page(EVENT_URL), EVENT_URL)
        self.assertEqual(metadata['status'], 'metadata_found')
        self.assertEqual(metadata['title'], 'PFL Lyon')
        self.assertEqual(metadata['date'], '2026-12-11')
        self.assertEqual(metadata['place'], 'Lyon, France')

    def test_missing_jsonld_and_html_metadata_requires_review(self):
        metadata = extract_event_metadata('<html></html>', EVENT_URL)
        self.assertEqual(metadata['status'], 'needs_review')
        self.assertEqual(metadata['reason'], 'fallback_title_missing_or_ambiguous')
        self.assertNotIn('date', metadata)

    def test_visible_date_does_not_borrow_year_from_another_date(self):
        html = ('<html><head><meta property="og:title" content="PFL Dubai"></head>'
                '<body><h2>PFL Dubai</h2><p>SAT NOV 14</p><p>Nov 13, 2026</p></body></html>')
        metadata = extract_event_metadata(html, 'https://pflmma.com/event/pfl-returns-to-dubai')
        self.assertEqual(metadata['status'], 'needs_review')
        self.assertEqual(metadata['title'], 'PFL Dubai')
        self.assertEqual(metadata['reason'], 'fallback_datetime_missing_or_ambiguous')
        self.assertNotIn('date', metadata)
        self.assertNotIn('start_at', metadata)

    def test_html_fallback_extracts_explicit_scoped_date(self):
        html = ('<h2 class="event-info-title">PFL Dubai</h2>'
                '<h2 class="event-sticky-title">PFL Dubai | SAT NOV 14 2026</h2>')
        metadata = extract_event_metadata(html, 'https://pflmma.com/event/pfl-returns-to-dubai')
        self.assertEqual(metadata['status'], 'metadata_found')
        self.assertEqual(metadata['title'], 'PFL Dubai')
        self.assertEqual(metadata['date'], '2026-11-14')
        self.assertEqual(metadata['start_at'], '')
        self.assertEqual(metadata['date_source'], 'scoped_html_explicit_year')

    def test_report_classifies_new_upcoming_event_without_writes(self):
        report = build_discovery_report(
            listing('pfl-lyon'),
            LISTING_URL,
            {EVENT_URL: event_page(EVENT_URL)},
            [],
            TODAY,
        )
        candidate = report['candidates'][0]
        self.assertEqual(candidate['proposal'], 'new_candidate')
        self.assertTrue(candidate['upcoming'])
        self.assertFalse(candidate['automatic_publication'])
        self.assertFalse(candidate['database_writes'])
        self.assertFalse(report['automatic_publication'])
        self.assertFalse(report['database_writes'])

    def test_report_matches_existing_event_by_canonical_url(self):
        existing = [{'id': 'pfl-1', 'url': 'https://www.pflmma.com/event/pfl-lyon/'}]
        report = build_discovery_report(
            listing('pfl-lyon'),
            LISTING_URL,
            {EVENT_URL: event_page(EVENT_URL)},
            existing,
            TODAY,
        )
        candidate = report['candidates'][0]
        self.assertEqual(candidate['proposal'], 'existing_event')
        self.assertEqual(report['summary']['existing_events'], 1)
        self.assertEqual(report['summary']['new_candidates'], 0)

    def test_past_event_is_not_marked_upcoming(self):
        report = build_discovery_report(
            listing('pfl-lyon'),
            LISTING_URL,
            {EVENT_URL: event_page(EVENT_URL, date='2026-11-15')},
            [],
            TODAY,
        )
        candidate = report['candidates'][0]
        self.assertFalse(candidate['upcoming'])
        self.assertEqual(report['summary']['upcoming'], 0)


if __name__ == '__main__':
    unittest.main()
