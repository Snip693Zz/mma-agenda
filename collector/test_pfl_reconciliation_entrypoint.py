import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pfl_reconciliation as reconciliation
import test_pfl_reconciliation_loader as loader_tests


class EntrypointTests(unittest.TestCase):
    def run_entrypoint(self, apply=False):
        tables = loader_tests.BaselineTests().fixture()
        client = loader_tests.Client(tables)
        report = {'mode': 'pfl_reconciliation_report', 'automatic_publication': False,
                  'summary': {'total': 0}, 'errors': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            argv = ['pfl_reconciliation.py', '--limit', '1', '--output', str(output),
                    '--discovery', 'discovery.json']
            if apply:
                argv.append('--apply')
            with patch('sys.argv', argv), \
                 patch.object(reconciliation, 'supabase_client', return_value=client), \
                 patch.object(reconciliation, 'load_discovery_candidates', return_value={'test': {}}) as discovery, \
                 patch.object(reconciliation, 'build_report', return_value=report) as build, \
                 patch.object(reconciliation, 'save_report', return_value={'status': 'recorded'}) as save, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(reconciliation.main(), 0)
            discovery.assert_called_once_with('discovery.json')
            events, fights = build.call_args.args
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['date'], '2026-11-14')
            self.assertEqual(fights['pfl-test'], [tables['fights'][1]])
            self.assertEqual(build.call_args.kwargs['discovery_candidates'], {'test': {}})
            written = json.loads(output.read_text())
            self.assertFalse(written['automatic_publication'])
            if apply:
                save.assert_called_once()
                self.assertIs(save.call_args.args[0], client)
                self.assertEqual(written['saved'], {'status': 'recorded'})
            else:
                save.assert_not_called()
                self.assertNotIn('saved', written)

    def test_report_uses_normalized_active_baseline_without_saving(self):
        self.run_entrypoint()

    def test_apply_still_saves_only_through_existing_report_function(self):
        self.run_entrypoint(apply=True)

    def test_invalid_baseline_stops_before_report_and_save(self):
        tables = loader_tests.BaselineTests().fixture()
        tables['event_cards'] = []
        with patch('sys.argv', ['pfl_reconciliation.py', '--apply']), \
             patch.object(reconciliation, 'supabase_client', return_value=loader_tests.Client(tables)), \
             patch.object(reconciliation, 'build_report') as build, \
             patch.object(reconciliation, 'save_report') as save:
            with self.assertRaises(ValueError):
                reconciliation.main()
            build.assert_not_called()
            save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
