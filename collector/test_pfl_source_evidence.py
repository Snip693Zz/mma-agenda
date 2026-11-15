"""Tests hors reseau des preuves brutes PFL."""
import unittest
from pfl_source_probe import inspect_html


class PFLEvidenceTests(unittest.TestCase):
    def test_jsonld_is_data_not_executed(self):
        html = '<script type="application/ld+json">{"@type":"SportsEvent","name":"Example"}</script>'
        report = inspect_html(html, 'https://pflmma.com/event/example')
        self.assertIn('SportsEvent', report['jsonld_samples'][0]['text'])
        self.assertFalse(report['jsonld_samples'][0]['truncated'])
        self.assertEqual(report['status'], 'unvalidated')

    def test_samples_are_bounded(self):
        html = '<script type="application/ld+json">' + 'x' * 4000 + '</script>'
        html += ('<div class="fighter">Example</div>' + ' ' * 1200) * 20
        report = inspect_html(html, 'https://pflmma.com/event/example')
        self.assertTrue(report['jsonld_samples'][0]['truncated'])
        self.assertEqual(len(report['html_samples']), 6)
        self.assertTrue(all(len(x['html']) <= 1000 for x in report['html_samples']))

    def test_calendar_reports_counts_before_truncation(self):
        html = ''.join('<h3>Event</h3><a href="/event/e-' + str(i) + '">Event</a>' for i in range(60))
        report = inspect_html(html, 'https://pflmma.com/events')
        self.assertEqual(report['heading_count'], 60)
        self.assertEqual(report['event_link_count'], 60)
        self.assertEqual(len(report['headings']), 20)
        self.assertEqual(len(report['event_links']), 40)
        self.assertEqual(report['html_samples'], [])
