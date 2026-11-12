import copy
import unittest
from types import SimpleNamespace
from publisher_control import control, RPC

ID = '47ef284c-5e4f-44ce-964b-c18e61b06f5a'
def fixture():
    report = {'mode':'read_only','database_read':True,'database_writes':False,'fallback_writes':False,'automatic_publication':False,'published':[],'errors':[]}
    journal = {'status':'recorded','agenda_writes':False,'receipt':{'run_id':ID,'report_sha256':'a'*64,'agenda_writes':False}}
    rows = {'ingest_runs':[{'id':ID,'status':'success','source_sha256':'a'*64,'extra':{'report':copy.deepcopy(report)}}], 'proposals':[{'id':'p','kind':'watch_only','status':'pending','event_id':None,'ingest_run_id':ID}]}
    return report,journal,Client(rows)

class Query:
    def __init__(self,rows): self.rows = rows
    def select(self,*a): return self
    def eq(self,*a): return self
    def order(self,*a): return self
    def range(self,start,end): self.rows = self.rows[start:end+1]; return self
    def execute(self): return SimpleNamespace(data=self.rows)

class Client:
    def __init__(self,rows): self.rows = rows; self.calls = []; self.probe = {'status':'disabled','agenda_writes':False,'journal_writes':False}
    def table(self,name): self.calls.append(('select',name)); return Query(self.rows[name])
    def rpc(self,name,args): self.calls.append((name,args)); return SimpleNamespace(execute=lambda:SimpleNamespace(data=self.probe))

class ControlTests(unittest.TestCase):
    def test_control_uses_only_null_probe(self):
        r,j,c = fixture(); before = copy.deepcopy((r,j,c.rows)); out = control(c,r,j)
        self.assertEqual(out['status'],'disabled_verified'); self.assertEqual(out['proposals'],{'watch_only':1}); self.assertEqual((r,j,c.rows),before)
        self.assertEqual(c.calls,[('select','ingest_runs'),('select','proposals'),(RPC,{'p_proposal_id':None})])
    def test_failed_journal_refused(self):
        r,j,c = fixture(); j['status'] = 'failed'
        with self.assertRaises(ValueError): control(c,r,j)
        self.assertFalse(c.calls)
    def test_error_report_refused(self):
        r,j,c = fixture(); r['errors'] = ['error']
        with self.assertRaises(ValueError): control(c,r,j)
        self.assertFalse(c.calls)
    def test_mismatched_report_refused(self):
        r,j,c = fixture(); c.rows['ingest_runs'][0]['extra']['report']['changed'] = True
        with self.assertRaises(ValueError): control(c,r,j)
        self.assertTrue(all(call[0] != RPC for call in c.calls))
    def test_bad_hash_refused(self):
        r,j,c = fixture(); c.rows['ingest_runs'][0]['source_sha256'] = 'b'*64
        with self.assertRaises(ValueError): control(c,r,j)
    def test_wrong_proposal_run_refused(self):
        r,j,c = fixture(); c.rows['proposals'][0]['ingest_run_id'] = 'other'
        with self.assertRaises(ValueError): control(c,r,j)
        self.assertTrue(all(call[0] != RPC for call in c.calls))
    def test_unexpected_publisher_state_refused(self):
        r,j,c = fixture(); c.probe['status'] = 'published'
        with self.assertRaises(ValueError): control(c,r,j)
    def test_already_recorded_receipt_accepted(self):
        r,j,c = fixture(); j['status'] = 'already_recorded'
        self.assertEqual(control(c,r,j)['status'],'disabled_verified')

if __name__ == '__main__': unittest.main()
