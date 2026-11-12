import copy
import unittest
from collector.ufc_proposals import build
URL='https://www.ufc.com/event/example'
def observed(pairs,status='parsed'):
 return {'source_url':URL,'status':status,'issues':[],'fights':[{'fighters':p,'source_kind':'official','source_url':URL} for p in pairs]}
def metadata(): return {'events':[{'source_url':URL,'source_kind':'official','method':'ufc_hero_timestamp','title':'UFC','date':'2027-01-01','start_at_utc':'2027-01-02T02:00:00+00:00'}]}
def baseline(pairs): return {'events':[{'id':'existing','org':'UFC','url':URL,'title':'Titre à préserver','cards':[{'fights':pairs,'start':'2027-01-02T02:00:00Z'}]}],'fighterRecords':{}}
def report(event): return {'events':[event],'errors':[]}
class ProposalTests(unittest.TestCase):
 def test_existing_event_unchanged(self):
  b=baseline([['A','B']]);before=copy.deepcopy(b)
  e=build(report(observed([['B','A']])),b,metadata())['entries'][0]
  self.assertEqual(e['type'],'unchanged');self.assertEqual(b,before);self.assertTrue(e['preserve_existing_cards'])
 def test_new_event_does_not_assign_header_time(self):
  e=build(report(observed([['A','B']])),{'events':[]},metadata())['entries'][0]
  self.assertEqual(e['type'],'create_event_proposal');self.assertIsNone(e['draft_event']['cards'][0]['start']);self.assertFalse(e['draft_event']['official']);self.assertFalse(e['ready_to_publish'])
 def test_missing_metadata_blocks_creation(self):
  self.assertEqual(build(report(observed([['A','B']])),{'events':[]},{'events':[]})['entries'][0]['type'],'blocked')
 def test_missing_fight_is_never_deleted(self):
  e=build(report(observed([['A','B']])),baseline([['A','B'],['C','D']]),metadata())['entries'][0]
  self.assertEqual(e['type'],'review_discrepancy');self.assertFalse(e['deletions_allowed']);self.assertEqual(e['existing_not_observed'],[['C','D']])
 def test_opponent_change_requires_review(self):
  e=build(report(observed([['A','C']])),baseline([['A','B']]),metadata())['entries'][0]
  self.assertEqual(e['type'],'review_discrepancy');self.assertEqual(e['new_pairs'],[['A','C']])
 def test_additions_preserve_existing_cards(self):
  e=build(report(observed([['A','B'],['C','D']])),baseline([['A','B']]),metadata())['entries'][0]
  self.assertEqual(e['type'],'add_fights_proposal');self.assertTrue(e['preserve_existing_cards'])
 def test_pending_is_watch_only(self):
  self.assertEqual(build(report(observed([],'pending_card')),{'events':[]},metadata())['entries'][0]['type'],'watch_only')
 def test_pending_cannot_hide_existing_fights(self):
  self.assertEqual(build(report(observed([],'pending_card')),baseline([['A','B']]),metadata())['entries'][0]['type'],'blocked')
 def test_ambiguous_url_blocks_publication(self):
  b=baseline([['A','B']]);b['events'].append({**b['events'][0],'id':'second'})
  self.assertEqual(build(report(observed([['A','B']])),b,metadata())['entries'][0]['type'],'blocked')
 def test_secondary_fight_is_not_upgraded(self):
  r=report(observed([['A','B']]));r['events'][0]['fights'][0]['source_kind']='secondary'
  self.assertEqual(build(r,{'events':[]},metadata())['entries'][0]['type'],'blocked')
 def test_duplicate_report_url_is_blocked(self):
  e=observed([['A','B']]);r={'events':[e,copy.deepcopy(e)],'errors':[]}
  self.assertTrue(all(x['type']=='blocked' for x in build(r,{'events':[]},metadata())['entries']))
 def test_reports_and_profiles_are_not_mutated(self):
  b=baseline([['A','B']]);b['fighterRecords']={'A':{'record':'unknown'}};r=report(observed([['A','B']]));m=metadata();before=copy.deepcopy((r,b,m));out=build(r,b,m)
  self.assertEqual((r,b,m),before);self.assertFalse(out['database_writes']);self.assertFalse(out['database_read']);self.assertFalse(out['fallback_writes'])
if __name__=='__main__': unittest.main()
