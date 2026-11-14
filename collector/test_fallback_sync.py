import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from fallback_sync import control,sync
from export_fallback import export

def result(kind='create_event',status='published'):
    item={'proposal_id':'p','event_id':'e','kind':kind,'status':status,'agenda_writes':status=='published','journal_writes':status=='published','inserted_fights':[],'card_position':None,'applied_updates':[]}
    if kind=='add_fight': item.update(inserted_fights=[{'fighters':['A','B']}],card_position=0)
    if kind=='update_event': item['applied_updates']=[{'field':'place','from':'Paris','to':'Lyon'}]
    return {'mode':'publisher_run','run_id':'run','status':status,'agenda_writes':status=='published','journal_writes':status=='published','results':[item],'published_count':int(status=='published')}
def rows():
    return {'events':[{'id':'e','org':'UFC','title':'UFC 999','event_date':'2099-01-01','url':'https://www.ufc.com/event/example','official_card_url':'https://www.ufc.com/event/example'}],'event_cards':[],'fights':[],'fighters':[]}
class Query:
    def __init__(self,data): self.data=list(data)
    def select(self,*a): return self
    def range(self,start,end): self.data=self.data[start:end+1];return self
    def execute(self): return SimpleNamespace(data=self.data)
class Client:
    def __init__(self,data): self.data=data
    def table(self,name): return Query(self.data[name])
class ControlTests(unittest.TestCase):
    def test_three_kinds_accepted(self):
        for kind in ('add_fight','update_event','create_event'):
            with self.subTest(kind=kind): self.assertEqual(control(result(kind))['status'],'ready')
    def test_disabled_refused(self):
        with self.assertRaises(ValueError): control(result(status='disabled'))
    def test_already_published_refused(self):
        with self.assertRaises(ValueError): control(result(status='already_published'))
    def test_failed_writes_refused(self):
        r=result();r['agenda_writes']=False
        with self.assertRaises(ValueError): control(r)
    def test_missing_add_fight_inserts_refused(self):
        r=result('add_fight');r['results'][0]['inserted_fights']=[]
        with self.assertRaises(ValueError): control(r)
    def test_bad_published_count_refused(self):
        r=result();r['published_count']=2
        with self.assertRaises(ValueError): control(r)
    def test_duplicate_proposal_refused(self):
        r=result();r['results']*=2;r['published_count']=2
        with self.assertRaises(ValueError): control(r)
    def test_missing_event_id_refused(self):
        r=result();r['results'][0].pop('event_id')
        with self.assertRaises(ValueError): control(r)
    def test_mixed_published_and_disabled(self):
        r=result();other=result('update_event','disabled')['results'][0];other['proposal_id']='other';r['results'].append(other)
        self.assertEqual(control(r)['proposal_ids'],['p'])
    def test_failed_entry_cannot_claim_writes(self):
        r=result();other=result('update_event','disabled')['results'][0];other.update(proposal_id='other',agenda_writes=True);r['results'].append(other)
        with self.assertRaises(ValueError): control(r)
class SyncTests(unittest.TestCase):
    def test_empty_event_uses_site_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'mma-data.json');out=sync(Client(rows()),result(),str(path));data=json.loads(path.read_text())
            self.assertEqual(set(data),{'version','events','fighterRecords'});self.assertEqual(data['version'],5);self.assertEqual(data['events'][0]['cards'],[]);self.assertEqual(data['events'][0]['date'],'2099-01-01');self.assertEqual((out['events'],out['cards'],out['fights']),(1,0,0));self.assertEqual(out['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
    def test_shared_export_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=Client(rows());path=Path(tmp,'mma-data.json');sync(client,result(),str(path));self.assertEqual(json.loads(path.read_text()),export(source_client=client))
    def test_second_sync_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp,'mma-data.json'));first=sync(Client(rows()),result(),path);second=sync(Client(rows()),result(),path)
            self.assertTrue(first['changed']);self.assertFalse(second['changed']);self.assertTrue(second['previous_had_content'])
    def test_active_cards_only_and_fighter_records_preserved(self):
        data=rows();data['event_cards']=[{'event_id':'e','position':0,'name':'Main','is_active':True,'start_at':None},{'event_id':'e','position':1,'name':'Old','is_active':False}];data['fights']=[{'event_id':'e','card_position':0,'position':0,'fighter_a':'A','fighter_b':'B'},{'event_id':'e','card_position':1,'position':0,'fighter_a':'C','fighter_b':'D'}];data['fighters']=[{'name':'A','record':'1-0','nc':0}]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'mma-data.json');out=sync(Client(data),result('add_fight'),str(path));rendered=json.loads(path.read_text())
            self.assertEqual((out['cards'],out['fights']),(1,1));self.assertEqual(rendered['events'][0]['cards'][0]['fights'],[['A','B']]);self.assertEqual(rendered['fighterRecords']['A']['record'],'1-0')
    def test_invalid_export_preserves_previous_file(self):
        data=rows();data['events'][0].pop('title')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'mma-data.json');path.write_text('previous')
            with self.assertRaises(ValueError): sync(Client(data),result(),str(path))
            self.assertEqual(path.read_text(),'previous')
    def test_empty_database_cannot_erase_fallback(self):
        data=rows();data['events']=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'mma-data.json');path.write_text('previous')
            with self.assertRaises(ValueError): sync(Client(data),result(),str(path))
            self.assertEqual(path.read_text(),'previous')
    def test_export_pagination(self):
        data=rows();data['fighters']=[{'name':str(i)} for i in range(1001)]
        self.assertEqual(len(export(source_client=Client(data))['fighterRecords']),1001)
if __name__=='__main__': unittest.main()
