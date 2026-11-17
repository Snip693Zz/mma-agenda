import unittest
from pfl_reconciliation_inputs import normalize_event, active_fights


class ReconciliationInputsTests(unittest.TestCase):
    def test_database_date_is_normalized_without_mutation(self):
        row = {'event_date': '2026-11-14'}
        self.assertEqual(normalize_event(row)['date'], '2026-11-14')
        self.assertNotIn('date', row)

    def test_conflicting_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_event({'event_date': '2026-11-14', 'date': '2026-11-15'})

    def test_missing_date_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_event({})

    def test_inactive_fights_are_excluded(self):
        cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
                 {'event_id': 'pfl-test', 'position': 1, 'is_active': True}]
        fights = [{'event_id': 'pfl-test', 'card_position': 0},
                  {'event_id': 'pfl-test', 'card_position': 1}]
        self.assertEqual(active_fights(cards, fights), [fights[1]])

    def test_unknown_card_is_rejected(self):
        with self.assertRaises(ValueError):
            active_fights([], [{'event_id': 'pfl-test', 'card_position': 0}])

    def test_legacy_null_state_remains_visible(self):
        card = {'event_id': 'pfl-test', 'position': 0, 'is_active': None}
        fight = {'event_id': 'pfl-test', 'card_position': 0}
        self.assertEqual(active_fights([card], [fight]), [fight])


if __name__ == '__main__':
    unittest.main()
