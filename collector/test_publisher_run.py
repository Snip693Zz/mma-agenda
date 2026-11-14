import unittest
from types import SimpleNamespace
from publisher_run import eligible_proposals, run

def report(): return {'mode':'read_only','database_read':True,'errors':[],'published':[]}
def journal(): return {'status':'recorded','agenda_writes':False,'receipt':{'run_id':'run','agenda_writes':False}}
def proposal(id='p',kind='add_fight',status='pending',run_id='run'):
    return dict(id=id,kind=kind,status=status,event_id='e',ingest_run_id=run_id)

class Query:
    def __init__(self,rows): self.rows = list(rows)
    def select(self,*a): return self
    def eq(self,column,value): self.rows = [r for r in self.rows if r.get(column) == value]; return self
    def in_(self,column,values): self.rows = [r for r in self.rows if r.get(column) in values]; return self
    def order(self,column): self.rows = sorted(self.rows,key=lambda r:r[column]); return self
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
        client = Client({'proposals':[proposal(kind='watch_only')]})
        self.assertEqual(run(client,report(),journal())['status'],'no_eligible_proposals'); self.assertFalse(client.calls)
    def test_add_fight_proposal_called(self):
        client = Client({'proposals':[proposal()]},{'p':{'status':'disabled','agenda_writes':False,'journal_writes':False}})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'not_published'); self.assertEqual(client.calls,[('publish_ufc_add_fights_v1',{'p_proposal_id':'p'})]); self.assertEqual(out['results'][0]['kind'],'add_fight'); self.assertEqual(out['results'][0]['status'],'disabled')
    def test_published_result_detected(self):
        client = Client({'proposals':[proposal()]},{'p':{'status':'published','agenda_writes':True,'journal_writes':True,'card_position':1,'inserted_fights':[{'id':'f'}]}})
        out = run(client,report(),journal())
        self.assertEqual(out['status'],'published'); self.assertEqual(out['published_count'],1); self.assertTrue(out['agenda_writes']); self.assertTrue(out['journal_writes'])
    def test_bad_journal_refused(self):
        client = Client({'proposals':[]}); j = journal(); j['status'] = 'failed'
        with self.assertRaises(ValueError): run(client,report(),j)
    def test_bad_report_refused(self):
        client = Client({'proposals':[]}); r = report(); r['errors'] = ['x']
        with self.assertRaises(ValueError): run(client,r,journal())
    def test_update_event_disabled(self):
        client = Client({'proposals':[proposal(kind='update_event')]},{'p':{'status':'disabled','agenda_writes':False,'journal_writes':False}})
        out = run(client,report(),journal())
        self.assertEqual(client.calls,[('publish_ufc_update_event_v1',{'p_proposal_id':'p'})]); self.assertEqual(out['status'],'not_published'); self.assertFalse(out['agenda_writes'])
    def test_update_event_result_preserved(self):
        changes = [{'field':'place','from':'A','to':'B'}]
        client = Client({'proposals':[proposal(kind='update_event')]},{'p':{'status':'published','agenda_writes':True,'journal_writes':True,'applied_updates':changes}})
        out = run(client,report(),journal())
        self.assertEqual(out['published_count'],1); self.assertEqual(out['results'][0]['applied_updates'],changes)
    def test_other_runs_statuses_and_kinds_excluded(self):
        rows = [proposal('a'),proposal('b','update_event'),proposal('c','watch_only'),proposal('d','create_event'),proposal('e',status='published'),proposal('f',run_id='other'),proposal('g',status='blocked'),proposal('h','review_discrepancy')]
        client = Client({'proposals':rows})
        self.assertEqual([p['id'] for p in eligible_proposals(client,'run')],['a','b','d']); self.assertFalse(client.calls)
    def test_pagination(self):
        kinds=['add_fight','update_event','create_event']
        rows = [proposal(str(i).zfill(4),kind=kinds[i%3]) for i in range(501)]
        client = Client({'proposals':rows})
        self.assertEqual(eligible_proposals(client,'run'),rows); self.assertEqual(len(client.rows['proposals']),501)
    def test_create_event_disabled(self):
        client=Client({'proposals':[proposal(kind='create_event')]},{'p':{'status':'disabled','agenda_writes':False,'journal_writes':False}})
        out=run(client,report(),journal())
        self.assertEqual(client.calls,[('publish_ufc_create_event_v1',{'p_proposal_id':'p'})]);self.assertEqual(out['status'],'not_published');self.assertFalse(out['agenda_writes']);self.assertEqual(out['published_count'],0)
    def test_create_event_without_fights(self):
        client=Client({'proposals':[proposal(kind='create_event')]},{'p':{'status':'published','event_id':'created','agenda_writes':True,'journal_writes':True,'inserted_fights':[]}})
        out=run(client,report(),journal())
        self.assertEqual(out['published_count'],1);self.assertEqual(out['results'][0]['event_id'],'created');self.assertEqual(out['results'][0]['inserted_fights'],[])
    def test_create_event_duplicate_not_published(self):
        client=Client({'proposals':[proposal(kind='create_event')]},{'p':{'status':'duplicate_requires_review','agenda_writes':False,'journal_writes':False}})
        out=run(client,report(),journal())
        self.assertEqual(out['status'],'not_published');self.assertEqual(out['published_count'],0);self.assertFalse(out['agenda_writes'])
    def test_mixed_kinds_route_to_separate_rpcs(self):
        rows=[proposal('a'),proposal('b','update_event'),proposal('c','create_event')]
        client=Client({'proposals':rows},{p['id']:{'status':'disabled','agenda_writes':False,'journal_writes':False} for p in rows})
        out=run(client,report(),journal())
        self.assertEqual([name for name,args in client.calls],['publish_ufc_add_fights_v1','publish_ufc_update_event_v1','publish_ufc_create_event_v1']);self.assertFalse(out['agenda_writes'])

if __name__ == '__main__': unittest.main()
