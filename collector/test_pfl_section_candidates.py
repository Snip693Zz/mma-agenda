"""Synthetic structure tests, not validation of live captures."""
import unittest
from pfl_section_candidates import diagnose_sections

URL = 'https://pflmma.com/event/example'


def row(i):
    return f'<div class="matchupRow" id="row{i}"><a href="/fighter/a{i}">A</a><a href="/fighter/b{i}">B</a></div>'


def run(content):
    return diagnose_sections('<div id="fight_card_component">' + content + '</div>', URL)


class SectionCandidateTests(unittest.TestCase):
    def test_chicago_shape_and_navigation_exclusion(self):
        report = run('<h2 id="main-tab">Main Card: 11 PM<a href="#prelim-tab">View Early Card</a></h2>' + ''.join(row(i) for i in range(4)) + '<h2 id="prelim-tab">Early Card<a href="#main-tab">View Main Card</a></h2>' + ''.join(row(i) for i in range(4, 13)))
        self.assertEqual(report['counts'], {'main_card': 4, 'early_card': 9})
        self.assertEqual(report['status'], 'review_required')
        self.assertFalse(report['database_writes'])
        self.assertFalse(report['automatic_publication'])
        self.assertFalse(report['event_identity_validated'])

    def test_lyon_date_only(self):
        report = run('<h2 id="main-tab">Sat, Dec 13 6:03 AM ET</h2>' + ''.join(row(i) for i in range(10)))
        self.assertEqual(report['counts'], {'unassigned': 10})

    def test_ambiguous_duplicate_and_conflicting_headings(self):
        for heading in ('<h2>Main Card Early Card</h2>', '<h2 id="main-tab">Early Card</h2>', '<h2 id="x">Main Card</h2><h2 id="x">Main Card</h2>', '<h2><a href="#main-tab">View Main Card</a></h2>'):
            with self.subTest(heading=heading):
                self.assertEqual(run(heading + row(0))['counts'], {'unassigned': 1})

    def test_nested_scope_does_not_leak(self):
        report = run('<section><h2>Main Card</h2>' + row(0) + '</section>' + row(1))
        self.assertEqual([r['section'] for r in report['rows']], ['main_card', 'unassigned'])

    def test_invalid_component_remains_in_review(self):
        report = diagnose_sections('', URL)
        self.assertEqual(report['status'], 'review_required')
        self.assertEqual(report['rows'], [])
