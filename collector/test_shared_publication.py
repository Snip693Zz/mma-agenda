"""Runner contract checks; PostgreSQL behavior is tested separately."""
import unittest
from unittest.mock import MagicMock
from shared_publication import run


class SharedPublicationTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.report = {'errors': [], 'automatic_publication': False,
                       'saved': {'ingest_run_id': 'test-run'},
                       'reports': [{'event_id': 'event-a'}, {'event_id': 'event-b'}]}
        self.client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {'id': 'event-a', 'org': 'PFL'}, {'id': 'event-b', 'org': 'PFL'}]
        self.client.rpc.return_value.execute.return_value.data = {'status': 'preview', 'agenda_writes': False}

    def test_preview_default_and_no_journal_write(self):
        result = run(self.client, self.report, 'PFL')
        self.assertEqual(result['failed_count'], 0)
        self.assertEqual(self.client.rpc.call_count, 2)
        for call in self.client.rpc.call_args_list:
            self.assertEqual(call.args[0], 'publish_event_additions_v1')
            self.assertIs(call.args[1]['p_apply'], False)

    def test_missing_journal_receipt_never_publishes(self):
        del self.report['saved']
        with self.assertRaises(ValueError):
            run(self.client, self.report, 'PFL', True)
        self.client.rpc.assert_not_called()

    def test_organization_mismatch_never_publishes(self):
        with self.assertRaises(ValueError):
            run(self.client, self.report, 'OTHER', True)
        self.client.rpc.assert_not_called()

    def test_one_event_failure_does_not_hide_other_result(self):
        response = MagicMock()
        response.data = {'status': 'already_present', 'agenda_writes': False}
        self.client.rpc.return_value.execute.side_effect = [RuntimeError('timeout'), response]
        result = run(self.client, self.report, 'PFL', True)
        self.assertEqual(result['failed_count'], 1)
        self.assertEqual(result['results'][0]['write_outcome'], 'unknown')
        self.assertEqual(result['results'][1]['status'], 'already_present')

    def test_duplicate_ids_are_rejected(self):
        self.report['reports'][1]['event_id'] = 'event-a'
        with self.assertRaises(ValueError):
            run(self.client, self.report, 'PFL')
        self.client.rpc.assert_not_called()
