import json
import unittest
from types import SimpleNamespace
from publisher_run import eligible_proposals, run

def report(): return {'mode':'read_only','database_read':True,'errors':[],'published':[]}
def journal(): return {'status':'recorded','agenda_writes':False,'receipt':{'run_id':'run','agenda_writes':False}}
class Query:
    def __init__(self,rows): self.rows = rows
    def select(self,*a): return self
    def eq(self,column,value): self.rows = [r for r in self.rows if r.get(column) == value]; return self
    def order(self,*a): return self
    def range(self,start,end): self.rows = self.rows[start:end+1]; return self
    def execute(self): return SimpleNamespace(data=self.rows)
class Rpc:
    def __init__(self,result): self.result = result
    def execute(self): return SimpleNamespace(data=self.result)
class Client:
    def __init__(self,rows,results=None): self.rows = rows; self.results = results or {}; self.calls = []
    def table(self,name): return Query(self.rows[name])
    def rpc(self,name,args):
        self.calls.append((name,args)); return Rpc(self.results.get(args['p_proposal_id'],{}))

class RunTests(unittest.TestCase):
    def test_no_eligible_proposals(self):
        client = Client({'proposals':[]})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'no_eligible_proposals'); self.assertEqual(out['published_count'],0); self.assertFalse(client.calls)
    def test_watch_only_not_called(self):
        client = Client({'proposals':[{'id':'w','kind':'watch_only','status':'pending','event_id':None,'ingest_run_id':'run'}]})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'no_eligible_proposals'); self.assertFalse(client.calls)
    def test_add_fight_proposal_called(self):
        client = Client({'proposals':[{'id':'p','kind':'add_fight','status':'pending','event_id':'e','ingest_run_id':'run'}]},{'p':{'status':'disabled','agenda_writes':False,'journal_writes':False}})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'not_published'); self.assertEqual(client.calls,[('publish_ufc_add_fights_v1',{'p_proposal_id':'p'})]); self.assertEqual(out['results'][0]['kind'],'add_fight'); self.assertEqual(out['results'][0]['status'],'disabled')
    def test_published_result_detected(self):
        client = Client({'proposals':[{'id':'p','kind':'add_fight','status':'pending','event_id':'e','ingest_run_id':'run'}]},{'p':{'status':'published','agenda_writes':True,'journal_writes':True,'card_position':1,'inserted_fights':[{'id':'f'}]}})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'published'); self.assertEqual(out['published_count'],1); self.assertTrue(out['agenda_writes']); self.assertTrue(out['journal_writes'])
    def test_bad_journal_refused(self):
        client = Client({'proposals':[]}); j = journal(); j['status'] = 'failed'
        with self.assertRaises(ValueError): run(client,report(),j)
    def test_bad_report_refused(self):
        client = Client({'proposals':[]}); r = report(); r['errors'] = ['x']
        with self.assertRaises(ValueError): run(client,r,journal())

if __name__ == '__main__': unittest.main()
