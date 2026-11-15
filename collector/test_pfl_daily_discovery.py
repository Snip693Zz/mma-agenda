"""Tests hors ligne du flux quotidien PFL : aucun réseau, aucune écriture."""
import json
import unittest
from pfl_daily_discovery import run_daily_discovery

LISTING_URL = 'https://pflmma.com/events'
EVENT_URL = 'https://pflmma.com/event/pfl-lyon'
TODAY = '2026-11-16'


def listing():
    return f'<html><body><a href="/event/pfl-lyon">Event</a></body></html>'


def event_page():
    payload = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': 'PFL Lyon',
        'startDate': '2026-12-11',
        'url': EVENT_URL,
        'location': {'name': 'Lyon, France'},
    }
    return f'<html><script type="application/ld+json">{json.dumps(payload)}</script></html>'


class FakeClient:
    def __init__(self, events):
        self._events = events

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return type('Result', (), {'data': self._rows})()

    def table(self, _name):
        return self._Query(self._events)


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.pages[url]


class DailyDiscoveryTests(unittest.TestCase):
    def test_report_is_built_without_database_writes(self):
        fetcher = FakeFetcher({LISTING_URL: listing(), EVENT_URL: event_page()})
        client = FakeClient([])
        report = run_daily_discovery(client, fetcher=fetcher, today=TODAY, limit=5, pause=lambda _seconds: None)
        self.assertEqual(report['mode'], 'pfl_discovery_report')
        self.assertFalse(report['automatic_publication'])
        self.assertFalse(report['database_writes'])
        self.assertEqual(report['summary']['new_candidates'], 1)
        self.assertEqual(report['summary']['pages_fetched'], 1)
        self.assertEqual(fetcher.calls, [LISTING_URL, EVENT_URL])

    def test_existing_event_is_not_proposed_for_creation(self):
        fetcher = FakeFetcher({LISTING_URL: listing(), EVENT_URL: event_page()})
        existing = [{'id': 'pfl-1', 'url': 'https://www.pflmma.com/event/pfl-lyon/'}]
        client = FakeClient(existing)
        report = run_daily_discovery(client, fetcher=fetcher, today=TODAY, limit=5, pause=lambda _seconds: None)
        self.assertEqual(report['candidates'][0]['proposal'], 'existing_event')
        self.assertEqual(report['summary']['new_candidates'], 0)

    def test_fetch_error_is_reported_without_stopping_other_pages(self):
        class FailingFetcher(FakeFetcher):
            def __call__(self, url):
                if url == EVENT_URL:
                    raise ValueError('Réponse PFL non valide')
                return super().__call__(url)

        fetcher = FailingFetcher({LISTING_URL: listing(), EVENT_URL: event_page()})
        client = FakeClient([])
        report = run_daily_discovery(client, fetcher=fetcher, today=TODAY, limit=5, pause=lambda _seconds: None)
        self.assertEqual(report['summary']['fetch_errors'], 1)
        self.assertEqual(report['errors'][0]['source_url'], EVENT_URL)
        self.assertEqual(report['summary']['pages_fetched'], 0)

    def test_limit_is_enforced(self):
        with self.assertRaises(ValueError):
            run_daily_discovery(FakeClient([]), fetcher=FakeFetcher({}), today=TODAY, limit=0, pause=lambda _seconds: None)


if __name__ == '__main__':
    unittest.main()
