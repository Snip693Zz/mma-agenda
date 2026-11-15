"""Offline regression coverage for repeated fighter links."""
import unittest
from pfl_card_structure import extract_pairs

URL = 'https://pflmma.com/event/test'


def card(*slugs):
    links = ''.join(f'<a href="/fighter/{slug}">INFO</a>' for slug in slugs)
    return '<div id="fight_card_component"><div class="matchupRow">' + links + '</div></div>'


class RepeatedLinkTests(unittest.TestCase):
    def test_two_distinct_fighters_with_repeated_links(self):
        result = extract_pairs(card('alpha', 'alpha', 'beta', 'beta', 'alpha', 'beta'), URL)
        self.assertEqual(result['status'], 'candidate_pairs')
        self.assertEqual(result['pairs'], [{'fighter_a_url': 'https://pflmma.com/fighter/alpha', 'fighter_b_url': 'https://pflmma.com/fighter/beta'}])
        self.assertEqual(result['duplicate_rows'], 0)
        self.assertFalse(result['automatic_publication'])
        self.assertFalse(result['database_writes'])
        self.assertFalse(result['event_identity_validated'])

    def test_only_one_distinct_fighter_repeated(self):
        result = extract_pairs(card('alpha', 'alpha'), URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'duplicate_fighter_in_row')
        self.assertEqual(result['pairs'], [])

    def test_three_distinct_fighters_remain_ambiguous(self):
        result = extract_pairs(card('alpha', 'alpha', 'beta', 'gamma'), URL)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['reason'], 'ambiguous_fighter_pair')
        self.assertEqual(result['pairs'], [])
