import copy
import unittest
from types import SimpleNamespace
from daily_refresh_readonly import load_live, run

class Fake:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def table(self, table):
        self.calls.append(('select', table))
        return Query(self.rows[table])

class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, fields): return self
    def order(self, field): return self
    def range(self, start, end): self.start, self.end = start, end; return self
    def execute(self): return SimpleNamespace(data=self.rows[self.start:self.end+1])

def fixture():
    return {'events': [{'id': 'e', 'org': 'UFC', 'event_date': '2027-01-01', 'official_card_url': 'https://www.ufc.com/event/test'}], 'event_cards': [{'event_id': 'e', 'position': 7, 'name': 'Liste non attribuée', 'start_at': None, 'level': 'official', 'source': 'UFC', 'extra': {'allocation': 'unassigned'}}], 'fights': [{'event_id': 'e', 'card_position': 7, 'position': 3, 'fighter_a': 'Jiří Procházka', 'fighter_b': 'Navajo Stirling'}]}

class ReadOnlyTests(unittest.TestCase):
    def test_real_supabase_columns(self):
        result = load_live(Fake(fixture()))
        self.assertEqual(result['events'][0]['cards'][0]['fights'], [['Jiří Procházka', 'Navajo Stirling']])
    def test_null_and_allocation_preserved(self):
        card = load_live(Fake(fixture()))['events'][0]['cards'][0]
        self.assertIsNone(card['start']); self.assertEqual(card['position'], 7); self.assertEqual(card['allocation'], 'unassigned')
    def test_date_and_official_url_adapted(self):
        event = load_live(Fake(fixture()))['events'][0]
        self.assertEqual(event['date'], '2027-01-01'); self.assertEqual(event['officialCardUrl'], 'https://www.ufc.com/event/test')
    def test_pagination(self):
        rows = fixture(); rows['fights'].append({**rows['fights'][0], 'position': 4, 'fighter_a': 'C', 'fighter_b': 'D'})
        self.assertEqual(len(load_live(Fake(rows), page_size=1)['events'][0]['cards'][0]['fights']), 2)
    def test_orphan_rejected(self):
        rows = fixture(); rows['fights'][0]['card_position'] = 0
        with self.assertRaises(ValueError): load_live(Fake(rows))
    def test_duplicate_rejected(self):
        rows = fixture(); rows['fights'].append(copy.deepcopy(rows['fights'][0]))
        with self.assertRaises(ValueError): load_live(Fake(rows))
    def test_no_write_and_publication_disabled(self):
        client = Fake(fixture())
        result = run(client, lambda baseline: ({}, {}), lambda a,b,c: {'entries': [{'type': 'create_event_proposal', 'ready_to_publish': True}], 'errors': []})
        self.assertFalse(result['database_writes']); self.assertFalse(result['automatic_publication']); self.assertEqual(result['published'], [])
        self.assertFalse(result['entries'][0]['ready_to_publish']); self.assertFalse(result['entries'][0]['auto_publishable'])
        self.assertEqual(client.calls, [('select','events'), ('select','event_cards'), ('select','fights')])
    def test_error_is_reported_without_secret(self):
        def fail(baseline): raise ValueError('SECRET-NEVER-LOG')
        result = run(Fake(fixture()), fail, lambda a,b,c: {})
        self.assertEqual(result['errors'][0]['phase'], 'collection'); self.assertNotIn('SECRET-NEVER-LOG', str(result))
    def test_empty_comparison_fails(self):
        result = run(Fake(fixture()), lambda baseline: ({}, {}), lambda a,b,c: {'entries': [], 'errors': []})
        self.assertTrue(result['errors'])

if __name__ == '__main__': unittest.main()
