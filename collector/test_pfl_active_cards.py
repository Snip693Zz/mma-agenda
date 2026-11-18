"""Regression checks: no historical-card alerts or invented Early Card allocation."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import pfl_reconciliation as pfl


def fight(a, b, card):
    return {'event_id': 'pfl-test', 'fighter_a': a, 'fighter_b': b,
            'card_position': card, 'position': 0}


class ActiveCardTests(unittest.TestCase):
    def test_only_explicitly_active_cards_are_compared(self):
        cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
                 {'event_id': 'pfl-test', 'position': 2, 'is_active': True},
                 {'event_id': 'other', 'position': 3, 'is_active': True}]
        fights = [fight('Old A', 'Old B', 0), fight('Live A', 'Live B', 2),
                  fight('Orphan A', 'Orphan B', 3)]
        before = deepcopy(fights)
        self.assertEqual(pfl.active_card_fights('pfl-test', fights, cards), [fights[1]])
        self.assertEqual(fights, before)

    def test_missing_active_cards_fails_closed(self):
        with self.assertRaises(ValueError):
            pfl.active_card_fights('pfl-test', [], [])

    def test_report_requires_card_metadata(self):
        report = pfl.build_report([{'id': 'pfl-test'}], {}, fetcher=lambda _: '')
        self.assertEqual(report['events_observed'], 0)
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(report['summary']['total'], 0)

    def test_report_filters_history_and_preserves_unknown_allocation(self):
        event = {'id': 'pfl-test', 'title': 'PFL Test', 'official': True,
                 'date': '2026-12-19', 'url': 'https://pflmma.com/event/pfl-test'}
        cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
                 {'event_id': 'pfl-test', 'position': 2, 'is_active': True}]
        existing = [fight('Old A', 'Old B', 0), fight('Live A', 'Live B', 2)]
        observed = [fight('Live A', 'Live B', 0), fight('New A', 'New B', 0)]
        with patch.object(pfl, 'extract_structured_fights', return_value=deepcopy(observed)), \
             patch.object(pfl, 'extract_event_identity', return_value=True), \
             patch.object(pfl, 'extract_event_date', return_value='2026-12-19'):
            report = pfl.build_report([event], {'pfl-test': existing}, fetcher=lambda _: '', cards=cards)
        self.assertFalse(report['errors'])
        self.assertEqual(report['summary']['total'], 1)
        proposal = report['reports'][0]['proposals'][0]
        self.assertEqual(proposal['kind'], 'add_fight')
        self.assertIsNone(proposal['payload']['card_position'])
        self.assertEqual(proposal['payload']['allocation'], 'unassigned')
        self.assertIs(proposal['auto_publishable'], False)
        self.assertIs(proposal['evidence']['publication_requires_card_assignment'], True)
        self.assertEqual(report['summary']['auto_publishable'], 0)
        self.assertIs(report['automatic_publication'], False)
        self.assertEqual(existing[0]['card_position'], 0)

    def test_active_absence_and_opponent_change_remain_review_only(self):
        event = {'id': 'pfl-test', 'title': 'PFL Test', 'official': True,
                 'date': '2026-12-19', 'url': 'https://pflmma.com/event/pfl-test'}
        existing = [fight('Current A', 'Same B', 2), fight('Missing A', 'Missing B', 2)]
        observed = [fight('Replacement A', 'Same B', 0)]
        with patch.object(pfl, 'extract_structured_fights', return_value=observed), \
             patch.object(pfl, 'extract_event_identity', return_value=True), \
             patch.object(pfl, 'extract_event_date', return_value='2026-12-19'):
            result = pfl.reconcile_event(event, existing, '')
        self.assertEqual(result['summary']['review_discrepancy'], 1)
        self.assertEqual(result['summary']['blocked'], 1)
        self.assertTrue(all(p['auto_publishable'] is False for p in result['proposals']))
