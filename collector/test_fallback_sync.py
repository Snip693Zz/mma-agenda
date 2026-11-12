import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from fallback_sync import control, sync

def result(status='published',inserted=1):
    return {'status':status,'agenda_writes':True,'journal_writes':True,'inserted_fights':[{'id':i} for i in range(inserted)],'card_position':1,'run_id':'run','proposal_id':'proposal'}

class Query:
    def __init__(self,rows): self.rows = rows
    def select(self,*a): return self
    def order(self,*a): return self
    def execute(self): return SimpleNamespace(data=self.rows)

class Client:
    def __init__(self,rows): self.rows = rows
    def table(self,name): return Query(self.rows[name])

class ControlTests(unittest.TestCase):
    def test_published_result_accepted(self):
        self.assertEqual(control(result())['status'],'ready')
    def test_already_published_refused(self):
        with self.assertRaises(ValueError): control(result('already_published'))
    def test_disabled_refused(self):
        with self.assertRaises(ValueError): control(result('disabled'))
    def test_missing_inserts_refused(self):
        with self.assertRaises(ValueError): control(result(inserted=0))
    def test_failed_writes_refused(self):
        r = result(); r['agenda_writes'] = False
        with self.assertRaises(ValueError): control(r)

class SyncTests(unittest.TestCase):
    def test_sync_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp,'mma-data.json'))
            client = Client({'events':[{'id':'e'}],'event_cards':[{'id':'c'}],'fights':[{'id':'f'}]})
            out = sync(client,result(),path)
            data = json.loads(Path(path).read_text())
            self.assertEqual(out['status'],'synced'); self.assertEqual((out['events'],out['cards'],out['fights']),(1,1,1))
            self.assertEqual(data['events'],[{'id':'e'}]); self.assertEqual(data['cards'],[{'id':'c'}]); self.assertEqual(data['fights'],[{'id':'f'}])
            self.assertEqual(out['sha256'],hashlib.sha256(Path(path).read_bytes()).hexdigest())
    def test_sync_preserves_previous_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp,'mma-data.json'); path.write_text('{"events":[]}',encoding='utf-8')
            client = Client({'events':[{'id':'e'}],'event_cards':[{'id':'c'}],'fights':[{'id':'f'}]})
            self.assertTrue(sync(client,result(),str(path))['previous_had_content'])

if __name__ == '__main__': unittest.main()
