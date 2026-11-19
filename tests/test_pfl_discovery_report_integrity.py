"""Régressions du rapport PFL, sans réseau ni accès Supabase."""
import unittest

from collector.pfl_discovery import build_discovery_report

LISTING = 'https://pflmma.com/events'
URL = 'https://pflmma.com/event/test'
TODAY = '2026-11-19'


class DiscoveryReportIntegrityTests(unittest.TestCase):
    def report(self, pages, existing=None, listing=None):
        return build_discovery_report(
            listing if listing is not None else f'<a href="{URL}">Test</a>',
            LISTING, pages, existing or [], TODAY,
        )

    def test_source_url_survives_missing_metadata(self):
        candidate = self.report({URL: '<html></html>'})['candidates'][0]
        self.assertEqual(candidate['source_url'], URL)
        self.assertEqual(candidate['metadata']['url'], URL)
        self.assertEqual(candidate['proposal'], 'review_required')

    def test_only_fetched_pages_are_classified(self):
        urls = [f'https://pflmma.com/event/test-{i:03}' for i in range(145)]
        listing = ''.join(f'<a href="{url}">Test</a>' for url in urls)
        report = self.report({url: '<html/>' for url in urls[:20]}, listing=listing)
        self.assertEqual(len(report['candidates']), 20)
        self.assertEqual(report['summary']['event_links'], 145)
        self.assertEqual(report['summary']['not_inspected'], 125)
        self.assertEqual(report['summary']['review_required'], 20)

    def test_existing_event_matches_without_metadata(self):
        report = self.report({URL: ''}, [{'official_card_url': URL}])
        self.assertEqual(report['candidates'][0]['proposal'], 'existing_event')

    def test_empty_pages_do_not_create_candidates(self):
        report = self.report({})
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['summary']['not_inspected'], 1)

    def test_missing_metadata_sets_diagnostic(self):
        report = self.report({URL: '<h1>Test</h1>'})
        self.assertTrue(report['diagnostics']['no_metadata_on_fetched_pages'])
        self.assertTrue(report['candidates'][0]['diagnostic']['has_h1'])

    def test_valid_metadata_and_read_only_flags(self):
        html = '<h1>Test PFL</h1><time datetime="2026-11-20"></time>'
        report = self.report({URL: html})
        candidate = report['candidates'][0]
        self.assertEqual(candidate['proposal'], 'new_candidate')
        self.assertTrue(candidate['upcoming'])
        self.assertFalse(report['diagnostics']['no_metadata_on_fetched_pages'])
        for item in (report, candidate):
            self.assertIs(item['automatic_publication'], False)
            self.assertIs(item['database_writes'], False)

    def test_unlisted_page_rejected(self):
        with self.assertRaises(ValueError):
            self.report({'https://pflmma.com/event/unlisted': ''})

    def test_no_links_diagnostic(self):
        self.assertTrue(self.report({}, listing='')['diagnostics']['no_event_links'])


if __name__ == '__main__':
    unittest.main()
