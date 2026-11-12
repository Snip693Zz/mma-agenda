import copy
import datetime as dt
import unittest
from publication_preview import plan, digest

NOW = dt.datetime(2026, 11, 12, 14, 0, tzinfo=dt.timezone.utc)
URL = 'https://www.ufc.com/event/test'

def fixture():
    event = {'id': 'e', 'org': 'UFC', 'date': '2027-01-01', 'url': URL, 'cards': [{'position': 0, 'start': '2027-01-01T20:00:00Z', 'level': 'official', 'source': URL, 'fights': [['A','B']]}]}
    item = {'type': 'add_fights_proposal', 'source_url': URL, 'existing_id': 'e', 'existing_sha256': digest(event), 'observed_fights': [['A','B'],['C','D']], 'new_pairs': [['C','D']], 'existing_not_observed': [], 'deletions_allowed': False}
    report = {'mode': 'read_only', 'database_read': True, 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'published': [], 'errors': [], 'cards_generated_at': NOW.isoformat(), 'entries': [copy.deepcopy(item)]}
    run = {'id': 'r', 'status': 'success', 'source_sha256': 'a'*64, 'extra': {'report': report}}
    proposal = {'id': 'p', 'kind': 'add_fight', 'status': 'pending', 'source_kind': 'official', 'source_url': URL, 'ingest_run_id': 'r', 'event_id': 'e', 'evidence': {'report_sha256': 'a'*64}, 'expires_at': (NOW+dt.timedelta(hours=24)).isoformat(), 'payload': item}
    return proposal, run, {'events': [event]}

class PreviewTests(unittest.TestCase):
    def test_creates_unassigned_card_not_card_zero(self):
        result = plan(*fixture(), NOW)
        self.assertEqual(result['decision'], 'candidate_add_fights'); self.assertEqual(result['target_card_position'], 1); self.assertTrue(result['create_unassigned_card']); self.assertFalse(result['agenda_writes'])
    def test_uses_explicit_unassigned_card(self):
        p,r,b = fixture(); b['events'][0]['cards'].append({'position': 7, 'allocation': 'unassigned', 'start': None, 'level': 'official', 'source': URL, 'fights': []})
        p['payload']['existing_sha256'] = digest(b['events'][0]); r['extra']['report']['entries'] = [copy.deepcopy(p['payload'])]
        result = plan(p,r,b,NOW); self.assertEqual(result['target_card_position'], 7); self.assertFalse(result['create_unassigned_card'])
    def test_expired_blocks(self):
        p,r,b = fixture(); p['expires_at'] = NOW.isoformat()
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_changed_event_blocks(self):
        p,r,b = fixture(); b['events'][0]['title'] = 'Changed'
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_already_present_is_noop(self):
        p,r,b = fixture(); b['events'][0]['cards'][0]['fights'].append(['C','D'])
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'already_present')
    def test_missing_existing_fight_blocks(self):
        p,r,b = fixture(); b['events'][0]['cards'][0]['fights'] = []
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_same_fighter_twice_blocks(self):
        p,r,b = fixture(); p['payload']['new_pairs'] = [['A','C']]; p['payload']['observed_fights'] = [['A','B'],['A','C']]; r['extra']['report']['entries'] = [copy.deepcopy(p['payload'])]
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_modified_payload_blocks(self):
        p,r,b = fixture(); p['payload']['new_pairs'] = [['E','F']]
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_ambiguous_event_blocks(self):
        p,r,b = fixture(); b['events'].append({**copy.deepcopy(b['events'][0]), 'id': 'other'})
        self.assertEqual(plan(p,r,b,NOW)['decision'], 'blocked')
    def test_watch_and_no_mutation(self):
        values = fixture(); before = copy.deepcopy(values); plan(*values,NOW); self.assertEqual(values,before)
        p,r,b = fixture(); p['kind'] = 'watch_only'; self.assertEqual(plan(p,r,b,NOW)['decision'], 'watch_only')

if __name__ == '__main__': unittest.main()
