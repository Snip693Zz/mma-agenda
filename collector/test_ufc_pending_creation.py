import copy
import unittest
from collector.ufc_proposals import build
URL='https://www.ufc.com/event/future-announcement'
def inputs():
 observed={'source_url':URL,'status':'pending_card','html_rows':0,'fights':[],'issues':[],'pending_evidence':{'visible_placeholder':'TBD vs TBD','event_metadata_checked':True,'athlete_links_found':False,'structured_fighter_fields_found':False}}
 cards={'generated_at':'2099-01-01T00:00:00Z','errors':[],'events':[observed]}
 baseline={'events':[]}
 catalog={'events':[{'source_url':URL,'source_kind':'official','method':'ufc_hero_timestamp','title':'UFC Fight Night','date':'2099-12-01'}]}
 return cards,baseline,catalog
class PendingCreationTests(unittest.TestCase):
 def test_verified_announcement_has_no_invented_cards(self):
  c,b,m=inputs();before=copy.deepcopy((c,b,m));r=build(c,b,m);e=r['entries'][0]
  self.assertEqual(e['type'],'create_event_proposal');self.assertEqual(e['draft_event']['cards'],[]);self.assertEqual(e['observed_fights'],[]);self.assertFalse(e['ready_to_publish']);self.assertTrue(e['requires_review']);self.assertFalse(r['database_writes']);self.assertEqual((c,b,m),before)
 def test_existing_empty_event_is_watch_only(self):
  c,b,m=inputs();b['events']=[{'id':'known','org':'UFC','url':URL,'cards':[]}]
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'watch_only')
 def test_existing_fights_never_hidden(self):
  c,b,m=inputs();b['events']=[{'id':'known','org':'UFC','url':URL,'cards':[{'fights':[['A','B']]}]}]
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_unverified_placeholder_stays_watch_only(self):
  c,b,m=inputs();c['events'][0].pop('pending_evidence')
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'watch_only')
 def test_metadata_required(self):
  c,b,m=inputs();m['events']=[]
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_secondary_metadata_refused(self):
  c,b,m=inputs();m['events'][0]['source_kind']='secondary'
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_invalid_date_refused(self):
  c,b,m=inputs();m['events'][0]['date']='2099-02-30'
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_past_date_refused(self):
  c,b,m=inputs();m['events'][0]['date']='2000-01-01'
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_missing_title_refused(self):
  c,b,m=inputs();m['events'][0]['title']=''
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_ambiguous_metadata_refused(self):
  c,b,m=inputs();other=copy.deepcopy(m['events'][0]);other['date']='2099-12-02';m['events'].append(other)
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_identifier_collision_refused(self):
  c,b,m=inputs();uid=build(c,b,m)['entries'][0]['draft_event']['id'];b['events']=[{'id':uid,'org':'PFL','url':'https://example.org'}]
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_unknown_page_not_promoted(self):
  c,b,m=inputs();c['events'][0]['status']='needs_review'
  self.assertEqual(build(c,b,m)['entries'][0]['type'],'blocked')
 def test_signals_prevent_creation(self):
  for field,value in [('athlete_links_found',True),('structured_fighter_fields_found',True),('event_metadata_checked',False)]:
   with self.subTest(field=field):
    c,b,m=inputs();c['events'][0]['pending_evidence'][field]=value
    self.assertNotEqual(build(c,b,m)['entries'][0]['type'],'create_event_proposal')

 def test_live_fetches_pending_metadata(self):
  import sys
  import types
  from unittest.mock import patch
  from collector.ufc_proposals import live
  c,b,m=inputs()
  review=types.ModuleType('collector.ufc_cards_review');review.collect_reviewed=lambda seed:copy.deepcopy(c)
  discover=types.ModuleType('collector.discover')
  class Client:
   def __init__(self,url): pass
   def get(self,url): return 'html'
  discover.Client=Client
  v2=types.ModuleType('collector.v2');v2.ufc_html=lambda html,url,today:(copy.deepcopy(m['events']),[],[])
  with patch.dict(sys.modules,{'collector.ufc_cards_review':review,'collector.discover':discover,'collector.v2':v2}):
   observed,catalog=live(b)
  self.assertEqual(build(observed,b,catalog)['entries'][0]['type'],'create_event_proposal')

if __name__=='__main__': unittest.main()
