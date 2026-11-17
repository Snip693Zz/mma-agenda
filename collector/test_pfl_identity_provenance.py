"""Offline regressions for PFL identity and date provenance."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pfl_primary_identity import primary_identity_matches
from pfl_daily_discovery import run_browser_discovery


class IdentityProvenanceTests(unittest.TestCase):
    def test_accent_and_suffix(self):
        event = {'title': 'PFL Dubaï — Nemkov vs Bilostenniy'}
        self.assertTrue(primary_identity_matches('<h1>PFL Dubai</h1>', event))
        self.assertTrue(primary_identity_matches('<meta property="og:title" content="PFL Dubai | Professional Fighters League">', event))

    def test_h2_requires_corroboration(self):
        event = {'title': 'PFL Lyon — Lapilus vs McKee'}
        meta = '<meta property="og:title" content="PFL Lyon | Professional Fighters League">'
        self.assertTrue(primary_identity_matches(meta + '<main><h2>PFL Lyon</h2></main>', event))
        self.assertFalse(primary_identity_matches('<main><h2>PFL Lyon</h2></main>', event))
        self.assertFalse(primary_identity_matches(meta + '<main><h2>PFL Lyon</h2><h2>PFL Lyon</h2></main>', event))
        self.assertFalse(primary_identity_matches(meta + '<main><h1>PFL Belfast</h1><h2>PFL Lyon</h2></main>', event))

    def test_wrong_city_and_partial_token_rejected(self):
        self.assertFalse(primary_identity_matches('<h1>PFL Dubai</h1>', {'title': 'PFL Lyon'}))
        self.assertFalse(primary_identity_matches('<h1>PFL Lyon</h1>', {'title': 'PFL Lyonnais'}))

    def test_date_provenance_survives_classification(self):
        candidate = {'source_url': 'https://pflmma.com/event/pfl-returns-to-dubai', 'title': 'PFL Dubai', 'date': '2026-11-14', 'date_source': 'boxemag_date', 'boxemag_date': '2026-11-14', 'boxemag_url': 'https://boxemag.ouest-france.fr/evenement/test/', 'page_html': '<h1>PFL Dubai</h1>', 'card_html': '<div>card</div>'}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'browser.json'
            target.write_text(json.dumps({'mode': 'pfl_browser_discovery', 'candidates': [candidate]}), encoding='utf-8')
            with patch('pfl_daily_discovery.load_pfl_events', return_value=[]):
                report = run_browser_discovery(None, str(target), '2026-11-17', 20)
        result = report['candidates'][0]
        for key in ('date_source', 'boxemag_date', 'boxemag_url'):
            self.assertEqual(result['metadata'][key], candidate[key])
        self.assertEqual(result['page_html'], candidate['page_html'])
        self.assertEqual(result['card_html'], candidate['card_html'])
        self.assertFalse(report['database_writes'])
        self.assertFalse(report['automatic_publication'])


if __name__ == '__main__':
    unittest.main()
