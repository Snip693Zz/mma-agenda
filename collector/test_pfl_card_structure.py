"""Offline structural regression tests; no network or database."""
import unittest
from pfl_card_structure import extract_pairs
from pfl_section_candidates import diagnose_sections

URL = 'https://pflmma.com/event/test'


def card(rows):
    return '<div id="fight_card_component">' + ''.join(rows) + '</div>'


def row(a, b, row_id='row-1'):
    return f'<div class="matchupRow" id="{row_id}"><a href="{a}">A</a><a href="{b}">B</a></div>'


class FightCardStructureTests(unittest.TestCase):
    def test_valid_card_extracts_distinct_pairs(self):
        html = card([row('/fighter/alpha', '/fighter/beta', 'row-1'), row('/fighter/gamma', '/fighter/delta', 'row-2')])
        result = extract_pairs(html, URL)
        self.assertEqual(result['status'], 'candidate_pairs')
        self.assertEqual(result['row_count'], 2)
        self.assertEqual(result['duplicate_rows'], 0)
        self.assertEqual(len(result['pairs']), 2)
        self.assertFalse(result['automatic_publication'])
        self.assertFalse(result['database_writes'])

    def test_duplicate_fighter_within_row_is_rejected(self):
        result = extract_pairs(card([row('/fighter/alpha', '/fighter/alpha')]), URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'duplicate_fighter_in_row')
        self.assertEqual(result['pairs'], [])

    def test_nested_card_component_is_rejected(self):
        html = '<div id="fight_card_component"><div id="fight_card_component">' + row('/fighter/alpha', '/fighter/beta') + '</div></div>'
        result = extract_pairs(html, URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'nested_card_component')
        self.assertEqual(result['pairs'], [])

    def test_invalid_fighter_url_is_rejected(self):
        result = extract_pairs(card([row('/fighter/alpha?x=1', '/fighter/beta')]), URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'invalid_fighter_url')
        self.assertEqual(result['pairs'], [])


class SectionEvidenceTests(unittest.TestCase):
    def test_explicit_unique_tabs_assign_sections(self):
        html = card([
            '<h2 id="main-tab">Main Card</h2>', row('/fighter/alpha', '/fighter/beta', 'row-1'),
            '<h2 id="prelim-tab">Early Card</h2>', row('/fighter/gamma', '/fighter/delta', 'row-2'),
        ])
        result = diagnose_sections(html, URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual([r['section'] for r in result['rows']], ['main_card', 'early_card'])
        self.assertEqual(result['counts'], {'main_card': 1, 'early_card': 1})
        self.assertFalse(result['automatic_publication'])

    def test_conflicting_or_duplicate_tab_leaves_rows_unassigned(self):
        html = card([
            '<h2 id="main-tab">Main Card Early Card</h2>', row('/fighter/alpha', '/fighter/beta', 'row-1'),
            '<h2 id="prelim-tab">Early Card</h2>', row('/fighter/gamma', '/fighter/delta', 'row-2'),
        ])
        result = diagnose_sections(html, URL)
        self.assertEqual([r['section'] for r in result['rows']], ['unassigned', 'early_card'])
        self.assertIsNone(result['rows'][0]['evidence'])

    def test_rows_without_explicit_section_remain_unassigned(self):
        result = diagnose_sections(card([row('/fighter/alpha', '/fighter/beta')]), URL)
        self.assertEqual(result['rows'][0]['section'], 'unassigned')
        self.assertIsNone(result['rows'][0]['evidence'])
        self.assertEqual(result['reason'], 'candidate_sections_only_identity_not_validated')
