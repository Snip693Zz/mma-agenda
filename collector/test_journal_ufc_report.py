import copy
import unittest
from types import SimpleNamespace
from journal_ufc_report import record, RPC

class Client:
    def __init__(self, replay=False): self.calls = []; self.replay = replay
    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={'run_id': '00000000-0000-0000-0000-000000000001', 'already_recorded': self.replay, 'report_sha256': 'a'*64, 'agenda_writes': False}))

def report():
    return {'mode': 'read_only', 'database_read': True, 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'published': [], 'errors': [], 'generated_at': '2026-11-12T13:28:45+00:00', 'cards_generated_at': '2026-11-12T13:28:46+00:00', 'entries': [{'type': 'watch_only', 'auto_publishable': False, 'ready_to_publish': False, 'deletions_allowed': False, 'requires_review': True}]}

class JournalTests(unittest.TestCase):
    def test_one_rpc_only_and_report_unchanged(self):
        client = Client(); data = report(); before = copy.deepcopy(data)
        result = record(client, data)
        self.assertEqual(data, before); self.assertEqual(client.calls, [(RPC, {'p_report': before})]); self.assertEqual(result['status'], 'recorded'); self.assertFalse(result['agenda_writes'])
    def test_duplicate_receipt_is_success(self):
        self.assertEqual(record(Client(True), report())['status'], 'already_recorded')
    def test_write_flags_refused_before_rpc(self):
        for flag in ('database_writes', 'fallback_writes', 'automatic_publication'):
            client = Client(); data = report(); data[flag] = True
            with self.assertRaises(ValueError): record(client, data)
            self.assertFalse(client.calls)
    def test_missing_flags_refused(self):
        client = Client(); data = report(); del data['database_read']
        with self.assertRaises(ValueError): record(client, data)
        self.assertFalse(client.calls)
    def test_empty_report_refused(self):
        data = report(); data['entries'] = []
        with self.assertRaises(ValueError): record(Client(), data)
    def test_publishable_entry_refused(self):
        client = Client(); data = report(); data['entries'][0]['auto_publishable'] = True
        with self.assertRaises(ValueError): record(client, data)
        self.assertFalse(client.calls)
    def test_error_report_can_be_journalled(self):
        data = report(); data['errors'] = [{'phase': 'metadata'}]
        self.assertEqual(record(Client(), data)['status'], 'recorded')

if __name__ == '__main__': unittest.main()
