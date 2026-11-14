import copy
import unittest
from collector.ufc_reallocation_plan import plan_reallocation
URL='https://www.ufc.com/event/test'

def fixtures():
    fights=[{'event_id':'test','card_position':0,'position':i,'fighter_a':a,'fighter_b':b} for i,(a,b) in enumerate([['Alpha','Beta'],['Gamma','Delta']])]
    event={'id':'test','org':'UFC','url':URL,'official_card_url':URL,'event_date':'2026-11-21','title':'UFC','place':'À confirmer','cards':[{'event_id':'test','position':0,'name':'Non attribués','start_at':None,'level':'official','source':URL,'extra':{'allocation':'unassigned'},'is_active':True,'fights':fights}]}
    details={'status':'parsed','mode':'details_read_only','database_writes':False,'automatic_publication':False,'issues':[],'source_url':URL,'source_sha256':'a'*64,'event_patch':{'title':'UFC — Alpha vs Beta','place':'Arena','date':'2026-11-21'},'cards':[{'name':'Préliminaires','start':'2026-11-21T15:00:00Z','source':URL,'level':'official','fights':[['Gamma','Delta']]},{'name':'Carte principale','start':'2026-11-21T18:00:00Z','source':URL,'level':'official','fights':[['Alpha','Beta']]}]}
    return event,details

class PlanTests(unittest.TestCase):
    def test_preserves_fights_and_never_mutates_inputs(self):
        event,details=fixtures(); before=copy.deepcopy((event,details))
        result=plan_reallocation(event,details)
        self.assertEqual(result['status'],'ready',result['issues'])
        self.assertEqual(result['preserved_fights'],2)
        self.assertEqual(sum(len(c['fights']) for c in result['projected_event']['cards']),2)
        self.assertEqual((event,details),before)
        self.assertFalse(result['database_writes'])
        self.assertFalse(any(a['operation'].startswith('delete') for a in result['actions']))
    def test_second_pass_is_unchanged(self):
        event,details=fixtures()
        first=plan_reallocation(event,details)
        second=plan_reallocation(first['projected_event'],details)
        self.assertEqual(second['status'],'unchanged',second['issues'])
        self.assertEqual(second['actions'],[])
    def test_official_source_label_matches_existing_card(self):
        event,details=fixtures()
        event['cards']=[{'event_id':'test','position':0,'name':'Préliminaires','start_at':'2026-11-21T15:00:00Z','level':'official','source':'Fiche officielle UFC','extra':{},'is_active':True,'fights':[{'event_id':'test','card_position':0,'position':0,'fighter_a':'Gamma','fighter_b':'Delta'}]},{'event_id':'test','position':1,'name':'Carte principale','start_at':'2026-11-21T18:00:00Z','level':'official','source':'Fiche officielle UFC','extra':{},'is_active':True,'fights':[{'event_id':'test','card_position':1,'position':0,'fighter_a':'Alpha','fighter_b':'Beta'}]}]
        result=plan_reallocation(event,details)
        self.assertEqual(result['status'],'unchanged',result['issues'])
        self.assertEqual(result['actions'],[])
    def test_missing_fight_blocks(self):
        e,d=fixtures();d['cards'][0]['fights']=[]
        self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_added_fight_blocks(self):
        e,d=fixtures();d['cards'][0]['fights'].append(['New','Other'])
        self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_duplicate_existing_fight_blocks(self):
        e,d=fixtures();f=copy.deepcopy(e['cards'][0]['fights'][0]);f['position']=2;e['cards'][0]['fights'].append(f)
        self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_duplicate_observation_blocks(self):
        e,d=fixtures();d['cards'][0]['fights'].append(['Beta','Alpha'])
        self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_wrong_identity_or_date_blocks(self):
        for field,value in [('org','PFL'),('event_date','2026-11-22')]:
            e,d=fixtures();e[field]=value
            self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_ambiguous_card_blocks(self):
        e,d=fixtures();r=plan_reallocation(e,d);e=r['projected_event'];c=copy.deepcopy(e['cards'][1]);c['position']=9;c['fights']=[];e['cards'].append(c)
        self.assertEqual(plan_reallocation(e,d)['status'],'blocked')
    def test_moves_use_new_positions_without_overwriting_old_slots(self):
        e,d=fixtures();r=plan_reallocation(e,d)
        self.assertEqual([a['card']['position'] for a in r['actions'] if a['operation']=='create_card'],[1,2])
        self.assertFalse(r['projected_event']['cards'][0]['is_active'])
    def test_error_never_exposes_partial_actions(self):
        e,d=fixtures();d['cards'][1]['start']='invalid'
        r=plan_reallocation(e,d)
        self.assertEqual(r['status'],'blocked')
        self.assertEqual(r['actions'],[])
        self.assertNotIn('projected_event',r)

if __name__=='__main__':
    unittest.main()
