"""Tests synthetiques du diagnostic ; aucune preuve de structure PFL reelle."""
import unittest
from pfl_source_probe import inspect_html


class PFLSourceProbeTests(unittest.TestCase):
    def test_links_are_filtered_and_deduplicated(self):
        html = '<a href="/event/lyon">A</a><a href="/event/lyon">B</a><a href="https://evil.example/event/x">X</a><a href="/news/x">N</a>'
        result = inspect_html(html, 'https://pflmma.com/events')
        self.assertEqual(result['event_links'], ['https://pflmma.com/event/lyon'])

    def test_headings_remain_unvalidated(self):
        result = inspect_html('<h3>PFL Dubai</h3><h1>PFL Lyon</h1>', 'https://pflmma.com/event/lyon')
        self.assertEqual([h['text'] for h in result['headings']], ['PFL Dubai', 'PFL Lyon'])
        self.assertEqual(result['status'], 'unvalidated')
        self.assertFalse(result['database_writes'])
        self.assertFalse(result['automatic_publication'])

    def test_script_metadata_and_hash(self):
        html = '<script type="application/ld+json">{}</script>'
        result = inspect_html(html, 'https://pflmma.com/event/lyon')
        self.assertEqual(result['scripts'], [{'type': 'application/ld+json'}])
        self.assertEqual(len(result['source_sha256']), 64)
        self.assertEqual(result, inspect_html(html, 'https://pflmma.com/event/lyon'))

    def test_unofficial_sources_are_rejected(self):
        for url in ('http://pflmma.com/events', 'https://pflmma.com.evil.example/events',
                    'https://pflmma.com/news/x', 'https://user@pflmma.com/events',
                    'https://pflmma.com:8443/events'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                inspect_html('', url)
