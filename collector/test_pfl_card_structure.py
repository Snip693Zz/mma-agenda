"""Exemples synthetiques bases sur les classes observees ; pas des captures reelles."""
import unittest
from pfl_card_structure import extract_pairs

URL = 'https://pflmma.com/event/example'


def row(*slugs):
    return '<div class="matchupRow">' + ''.join('<a href="/fighter/' + slug + '">INFO</a>' for slug in slugs) + '</div>'


def component(content):
    return '<div id="fight_card_component">' + content + '</div>'


class PFLCardStructureTests(unittest.TestCase):
    def test_repeated_links_and_expanded_view_do_not_duplicate(self):
        result = extract_pairs(component(row('a', 'a', 'b', 'b', 'a', 'b')), URL)
        self.assertEqual(len(result['pairs']), 1)
        self.assertFalse(result['automatic_publication'])
        self.assertFalse(result['event_identity_validated'])

    def test_outside_content_is_ignored(self):
        result = extract_pairs(row('outside-a', 'outside-b') + component(row('a', 'b')), URL)
        self.assertEqual(result['row_count'], 1)
        self.assertEqual(result['pairs'][0]['fighter_a_url'], 'https://pflmma.com/fighter/a')

    def test_duplicate_rows_are_reported(self):
        result = extract_pairs(component(row('a', 'b') + row('b', 'a')), URL)
        self.assertEqual(len(result['pairs']), 1)
        self.assertEqual(result['duplicate_rows'], 1)

    def test_empty_or_truncated_is_not_a_valid_card(self):
        for html in ('', component('<style>.fightcard { display:none; }</style>'), component(row('a', 'b'))[:-6]):
            with self.subTest(html=html):
                self.assertEqual(extract_pairs(html, URL)['status'], 'review_required')

    def test_ambiguous_row_rejects_entire_extraction(self):
        for slugs in (('a',), ('a', 'b', 'c')):
            result = extract_pairs(component(row('x', 'y') + row(*slugs)), URL)
            self.assertEqual(result['pairs'], [])
            self.assertEqual(result['reason'], 'ambiguous_fighter_pair')

    def test_external_fighter_is_rejected(self):
        html = component(row('a', 'b').replace('href="/fighter/a"', 'href="https://evil.example/fighter/a"'))
        self.assertEqual(extract_pairs(html, URL)['reason'], 'invalid_fighter_url')

    def test_wrong_source_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_pairs(component(row('a', 'b')), 'https://evil.example/event/example')

    def test_multiple_components_are_rejected(self):
        result = extract_pairs(component(row('a', 'b')) + component(row('c', 'd')), URL)
        self.assertEqual(result['status'], 'review_required')
