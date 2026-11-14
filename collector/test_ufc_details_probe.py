import hashlib
import unittest
from collector.ufc_details_probe import inspect_html, URL

class ProbeTests(unittest.TestCase):
    def test_explicit_signals_preserved(self):
        html = '<h1>UFC Test</h1><section id="main-card"><h2>Main Card</h2><time data-timestamp="1795284000">1:00 PM EST</time><li class="c-listing-fight">Alpha vs Beta</li></section>'
        report = inspect_html(html)
        self.assertEqual(report['fight_rows'], 1)
        self.assertEqual(report['source_sha256'], hashlib.sha256(html.encode()).hexdigest())
        self.assertTrue(any(s['timestamp']=='1795284000' for s in report['signals']))
        self.assertFalse(report['database_writes'])
        self.assertFalse(report['automatic_publication'])
        self.assertNotIn('cards', report)
    def test_script_noise_not_in_visible_text(self):
        report = inspect_html('<div class="hero">Title<script>FAKE</script><style>NOISE</style></div>')
        self.assertEqual(report['signals'][0]['text'], 'Title')
    def test_empty_page_not_a_confirmed_empty_card(self):
        report = inspect_html('<h1>UFC</h1>')
        self.assertEqual(report['fight_rows'], 0)
        self.assertNotIn('card_empty_confirmed', report)
    def test_rejects_nonofficial_and_ambiguous_urls(self):
        for url in ('https://evil.example/event/test','http://www.ufc.com/event/test','https://user@www.ufc.com/event/test','https://www.ufc.com/events','https://www.ufc.com/event/test?x=1','https://www.ufc.com:444/event/test'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                inspect_html('', url)
    def test_nested_unicode_and_duplicate_rows_are_raw_evidence(self):
        html = '<h1>UFC — <b>Procházka</b></h1><li class="c-listing-fight">A vs B</li><li class="c-listing-fight">A vs B</li>'
        report = inspect_html(html, URL)
        self.assertEqual(report['headings'][0]['text'], 'UFC — Procházka')
        self.assertEqual(report['fight_rows'], 2)

if __name__ == '__main__':
    unittest.main()
