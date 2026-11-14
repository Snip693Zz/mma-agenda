import copy
import unittest
from collector.ufc_daily_reconciliation import reconcile, reconcile_event, to_planner_event

URL='https://www.ufc.com/event/test'

def fixtures():
    live={'id':'test','org':'UFC','url':URL,'officialCardUrl':URL,'date':'2026-11-21','title':'UFC','place':'À confirmer','cards':[{'position':0,'name':'Non attribués','start':None,'level':'official','source':URL,'extra':{'allocation':'unassigned'},'is_active':True,'fights':[['Alpha','Beta'],['Gamma','Delta']]}]}
    details={'status':'parsed','mode':'details_read_only','database_writes':False,'automatic_publication':False,'issues':[],'source_url':URL,'source_sha256':'a'*64,'event_patch':{'title':'UFC — Alpha vs Beta','place':'Arena','date':'2026-11-21'},'cards':[{'name':'Préliminaires','start':'2026-11-21T15:00:00Z','source':URL,'level':'official','fights':[['Gamma','Delta']]},{'name':'Carte principale','start':'2026-11-21T18:00:00Z','source':URL,'level':'official','fights':[['Alpha','Beta']]}]}
    return live,details

def projected_to_live(projected):
    return {'id':projected['id'],'org':projected['org'],'url':projected['url'],'officialCardUrl':projected['official_card_url'],'date':projected['event_date'],'title':projected['title'],'place':projected['place'],'cards':[{'position':c['position'],'name':c['name'],'start':c['start_at'],'level':c['level'],'source':c['source'],'extra':c['extra'],'is_active':c['is_active'],'fights':[[f['fighter_a'],f['fighter_b']] for f in c['fights']]} for c in projected['cards']]}

class ReconciliationTests(unittest.TestCase):
    def test_ready_reallocation_is_read_only(self):
        live,details=fixtures(); before=copy.deepcopy((live,details))
        entry=reconcile_event(live,details)
        self.assertEqual(entry['status'],'reallocation_ready',entry['issues'])
        self.assertEqual(entry['preserved_fights'],2)
        self.assertEqual(entry['action_counts']['move_fight'],2)
        self.assertFalse(entry['database_writes'])
        self.assertFalse(entry['automatic_publication'])
        self.assertTrue(entry['requires_review'])
        self.assertFalse(entry['ready_to_publish'])
        self.assertNotIn('projected_event',entry)
        self.assertEqual((live,details),before)
    def test_second_pass_is_unchanged(self):
        live,details=fixtures()
        first=reconcile_event(live,details)
        self.assertEqual(first['status'],'reallocation_ready')
        projected={'id':'test','org':'UFC','url':URL,'official_card_url':URL,'event_date':'2026-11-21','title':'UFC — Alpha vs Beta','place':'Arena','cards':[{'event_id':'test','position':1,'name':'Préliminaires','start_at':'2026-11-21T15:00:00Z','level':'official','source':URL,'extra':{},'is_active':True,'fights':[{'event_id':'test','card_position':1,'position':0,'fighter_a':'Gamma','fighter_b':'Delta'}]},{'event_id':'test','position':2,'name':'Carte principale','start_at':'2026-11-21T18:00:00Z','level':'official','source':URL,'extra':{},'is_active':True,'fights':[{'event_id':'test','card_position':2,'position':0,'fighter_a':'Alpha','fighter_b':'Beta'}]}]}
        second=reconcile_event(projected_to_live(projected),details)
        self.assertEqual(second['status'],'unchanged',second['issues'])
        self.assertEqual(second['action_counts'],{})
    def test_non_parsed_details_are_watch_only(self):
        live,details=fixtures()
        for status,issues in [('needs_review',['Aucune carte exploitable']),('needs_review',['Page UFC en direct : structure non exploitable']),('error',['Extraction indisponible'])]:
            payload=copy.deepcopy(details);payload['status']=status;payload['issues']=issues
            entry=reconcile_event(live,payload)
            self.assertEqual(entry['status'],'watch_only',entry['issues'])
            self.assertEqual(entry['action_counts'],{})
            self.assertEqual(entry['issues'],issues)
    def test_missing_or_added_fight_blocks(self):
        live,details=fixtures()
        missing=copy.deepcopy(details);missing['cards'][0]['fights']=[]
        self.assertEqual(reconcile_event(live,missing)['status'],'blocked')
        added=copy.deepcopy(details);added['cards'][0]['fights'].append(['New','Other'])
        self.assertEqual(reconcile_event(live,added)['status'],'blocked')
    def test_missing_details_is_watch_only(self):
        live,_=fixtures()
        report=reconcile({'events':[live]},{})
        self.assertEqual(report['entries'][0]['status'],'watch_only')
        self.assertEqual(report['summary'],{'watch_only':1})
    def test_conversion_preserves_pairs_and_positions(self):
        live,_=fixtures()
        event=to_planner_event(live)
        self.assertEqual(event['cards'][0]['fights'][0]['fighter_a'],'Alpha')
        self.assertEqual(event['cards'][0]['fights'][1]['position'],1)
    def test_reconcile_rejects_invalid_baseline(self):
        with self.assertRaises(ValueError):
            reconcile({},{});

if __name__=='__main__':
    unittest.main()
