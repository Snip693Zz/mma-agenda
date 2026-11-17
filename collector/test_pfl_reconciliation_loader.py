import unittest
from types import SimpleNamespace
from pfl_reconciliation_loader import load_baseline, read_rows


class Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.bounds = (0, 499)

    def select(self, fields):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def order(self, field):
        return self

    def range(self, start, end):
        self.bounds = (start, end)
        return self

    def execute(self):
        start, end = self.bounds
        return SimpleNamespace(data=self.rows[start:end + 1])


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self.tables[name])


class BaselineTests(unittest.TestCase):
    def fixture(self):
        return {
            'events': [{'id': 'pfl-test', 'org': 'PFL', 'event_date': '2026-11-14'},
                       {'id': 'ufc-test', 'org': 'UFC', 'event_date': '2026-11-14'}],
            'event_cards': [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
                            {'event_id': 'pfl-test', 'position': 2, 'is_active': True}],
            'fights': [{'event_id': 'pfl-test', 'card_position': 0, 'position': 0, 'fighter_a': 'Old A', 'fighter_b': 'Old B'},
                       {'event_id': 'pfl-test', 'card_position': 2, 'position': 0, 'fighter_a': 'A', 'fighter_b': 'B'}],
        }

    def test_database_contract_and_inactive_cards(self):
        tables = self.fixture()
        events, fights = load_baseline(Client(tables))
        self.assertEqual([event['id'] for event in events], ['pfl-test'])
        self.assertEqual(events[0]['date'], '2026-11-14')
        self.assertNotIn('date', tables['events'][0])
        self.assertEqual(fights['pfl-test'], [tables['fights'][1]])
        self.assertEqual(fights['pfl-test'][0]['card_position'], 2)

    def test_empty_database(self):
        self.assertEqual(load_baseline(Client({'events': []})), ([], {}))

    def test_unknown_card_blocks_baseline(self):
        tables = self.fixture()
        tables['event_cards'] = []
        with self.assertRaises(ValueError):
            load_baseline(Client(tables))

    def test_invalid_date_blocks_baseline(self):
        tables = self.fixture()
        tables['events'][0]['event_date'] = 'invalid'
        with self.assertRaises(ValueError):
            load_baseline(Client(tables))

    def test_read_paginates(self):
        rows = [{'position': i} for i in range(1001)]
        self.assertEqual(read_rows(Query(rows)), rows)

    def test_negative_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            load_baseline(Client({}), -1)


if __name__ == '__main__':
    unittest.main()
