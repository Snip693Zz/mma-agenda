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
    def test_event_links_are_canonical_and_deduplicated(self):
        html = listing('pfl-lyon', 'pfl-lyon', '2026-chicago2')
        links = extract_event_links(html, LISTING_URL)
        self.assertEqual(links, [
            'https://pflmma.com/event/2026-chicago2',
            'https://pflmma.com/event/pfl-lyon',
        ])

    def test_metadata_is_extracted_from_matching_jsonld(self):
        metadata = extract_event_metadata(event_page(EVENT_URL), EVENT_URL)
        self.assertEqual(metadata['status'], 'metadata_found')
        self.assertEqual(metadata['title'], 'PFL Lyon')
        self.assertEqual(metadata['date'], '2026-12-11')
        self.assertEqual(metadata['place'], 'Lyon, France')

    def test_missing_or_ambiguous_jsonld_requires_review(self):
        metadata = extract_event_metadata('<html></html>', EVENT_URL)
        self.assertEqual(metadata['status'], 'needs_review')
        self.assertEqual(metadata['reason'], 'metadata_not_found')

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
