import copy,unittest
from daily_refresh import build
URL='https://www.ufc.com/event/example'
def observed(pairs,status='parsed'):return {'source_url':URL,'status':status,'issues':[],'fights':[{'fighters':p,'source_kind':'official','source_url':URL} for p in pairs]}
def metadata(title='UFC',place=None,date='2027-01-01',kind='official'):return {'events':[{'source_url':URL,'source_kind':kind,'method':'ufc_hero_timestamp','title':title,'place':place,'date':date,'start_at_utc':'2027-01-02T02:00:00+00:00','start_at_paris':'2027-01-02T03:00:00+01:00'}]}
def live(pairs=None,title='UFC',place='Ancienne salle',event_date='2027-01-01'):
 if pairs is None:pairs=[['A','B']]
 return {'events':[{'id':'existing','url':URL,'official_card_url':URL,'title':title,'place':place,'event_date':event_date,'cards':[{'position':0,'fights':pairs}]}],'fighterRecords':{}}
def report(event):return {'events':[event],'errors':[]}
class DailyTests(unittest.TestCase):
 def test_new_event_is_auto_publishable_without_card_time(self):
  e=build(report(observed([['A','B']])),{'events':[]},metadata())['entries'][0]
  self.assertEqual(e['kind'],'create_event');self.assertTrue(e['auto_publishable']);self.assertIsNone(e['payload']['card']['start']);self.assertFalse(e['payload']['event']['official'])
 def test_existing_event_unchanged(self):
  out=build(report(observed([['B','A']])),live(),metadata())
  self.assertEqual(out['summary'],{'watch_only':1})
 def test_new_pair_is_auto_publishable(self):
  e=build(report(observed([['A','B'],['C','D']])),live(),metadata())['entries'][0]
  self.assertEqual(e['kind'],'add_fight');self.assertTrue(e['auto_publishable']);self.assertEqual(e['payload']['fights'],[['C','D']])
 def test_missing_existing_fight_blocks(self):
  e=build(report(observed([['A','B']])),live([['A','B'],['C','D']]),metadata())['entries'][0]
  self.assertEqual(e['kind'],'review_discrepancy');self.assertEqual(e['status'],'blocked');self.assertFalse(e['deletions_allowed'])
 def test_opponent_change_blocks(self):
  e=build(report(observed([['A','C']])),live([['A','B']]),metadata())['entries'][0]
  self.assertEqual(e['kind'],'review_discrepancy');self.assertEqual(e['status'],'blocked')
 def test_pending_cannot_hide_existing_fights(self):
  e=build(report(observed([],'pending_card')),live(),metadata())['entries'][0]
  self.assertEqual(e['kind'],'review_discrepancy');self.assertEqual(e['status'],'blocked')
 def test_pending_without_existing_is_watch_only(self):
  e=build(report(observed([],'pending_card')),{'events':[]},metadata())['entries'][0]
  self.assertEqual(e['kind'],'watch_only');self.assertFalse(e['auto_publishable'])
 def test_secondary_fight_is_blocked(self):
  r=report(observed([['A','B']]));r['events'][0]['fights'][0]['source_kind']='secondary'
  self.assertEqual(build(r,{'events':[]},metadata())['entries'][0]['status'],'blocked')
 def test_duplicate_url_is_blocked(self):
  e=observed([['A','B']]);r={'events':[e,copy.deepcopy(e)],'errors':[]}
  self.assertTrue(all(x['status']=='blocked' for x in build(r,{'events':[]},metadata())['entries']))
 def test_title_refinement_is_auto_publishable(self):
  out=build(report(observed([['A','B']])),live(title='UFC 335'),metadata(title='UFC 335 — Oliveira vs Lopes'))
  updates=[e for e in out['entries'] if e['kind']=='update_event']
  self.assertEqual(len(updates),1);self.assertEqual(updates[0]['status'],'auto_publishable');self.assertEqual(updates[0]['payload']['values'],{'title':'UFC 335 — Oliveira vs Lopes'})
 def test_place_change_is_auto_publishable(self):
  out=build(report(observed([['A','B']])),live(),metadata(place='Nouvelle salle'))
  updates=[e for e in out['entries'] if e['kind']=='update_event']
  self.assertEqual(len(updates),1);self.assertEqual(updates[0]['status'],'auto_publishable');self.assertEqual(updates[0]['payload']['values'],{'place':'Nouvelle salle'})
 def test_date_change_requires_review(self):
  out=build(report(observed([['A','B']])),live(),metadata(date='2027-01-08'))
  updates=[e for e in out['entries'] if e['kind']=='update_event']
  self.assertEqual(len(updates),1);self.assertEqual(updates[0]['status'],'blocked');self.assertFalse(updates[0]['auto_publishable']);self.assertEqual(updates[0]['payload']['values'],{'event_date':'2027-01-08'})
 def test_non_official_metadata_creates_no_update(self):
  out=build(report(observed([['A','B']])),live(),metadata(kind='secondary'))
  self.assertFalse(any(e['kind']=='update_event' for e in out['entries']))
 def test_no_deletion_or_mutation(self):
  l=live([['A','B']]);before=copy.deepcopy(l);r=report(observed([['A','B']]));m=metadata();out=build(r,l,m)
  self.assertEqual(l,before);self.assertFalse(out['database_read'] is False);self.assertEqual(out['summary'],{'watch_only':1})
if __name__=='__main__':unittest.main()
