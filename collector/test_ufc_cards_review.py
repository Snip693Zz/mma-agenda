import copy
import unittest
from collector.ufc_cards_review import classify_empty,successful
URL='https://www.ufc.com/event/test'
META=[{'source_url':URL,'source_kind':'official','method':'ufc_hero_timestamp'}]
def empty(): return {'source_url':URL,'status':'needs_review','html_rows':0,'fights':[],'issues':[]}
class PendingTests(unittest.TestCase):
 def test_verified_placeholder_is_pending(self):
  r=classify_empty(empty(),'<h1>UFC</h1><p>TBD <b>vs</b> TBD</p>',META)
  self.assertEqual(r['status'],'pending_card');self.assertFalse(r['card_empty_confirmed'])
 def test_unknown_layout_still_requires_review(self):
  self.assertEqual(classify_empty(empty(),'<h1>UFC</h1>',META)['status'],'needs_review')
 def test_metadata_must_be_verified(self):
  self.assertEqual(classify_empty(empty(),'TBD vs TBD',[])['status'],'needs_review')
 def test_metadata_must_match_the_event(self):
  other=copy.deepcopy(META);other[0]['source_url']='https://www.ufc.com/event/other'
  self.assertEqual(classify_empty(empty(),'TBD vs TBD',other)['status'],'needs_review')
 def test_previously_known_card_cannot_be_downgraded_to_pending(self):
  r=empty();r['comparison']={'baseline_count':12}
  self.assertEqual(classify_empty(r,'TBD vs TBD',META)['status'],'needs_review')
 def test_athlete_link_blocks_empty_classification(self):
  self.assertEqual(classify_empty(empty(),'TBD vs TBD<a href="/athlete/someone">A</a>',META)['status'],'needs_review')
 def test_structured_fighter_field_blocks_empty_classification(self):
  html='TBD vs TBD<script type="application/ld+json">{"competitor":[{"name":"A"}]}</script>'
  self.assertEqual(classify_empty(empty(),html,META)['status'],'needs_review')
 def test_script_placeholder_is_not_visible_evidence(self):
  self.assertEqual(classify_empty(empty(),'<script>TBD vs TBD</script>',META)['status'],'needs_review')
 def test_incomplete_fight_row_remains_a_failure(self):
  r=empty();r['html_rows']=1;r['issues']=[{'reason':'missing fighter'}]
  self.assertEqual(classify_empty(r,'TBD vs TBD',META)['status'],'needs_review')
 def test_success_does_not_hide_errors_or_unknown_statuses(self):
  report={'events':[{'status':'parsed'},{'status':'pending_card'}],'errors':[]}
  self.assertTrue(successful(report));report['events'].append({'status':'needs_review'});self.assertFalse(successful(report))
  report={'events':[{'status':'parsed'}],'errors':[{'reason':'HTTP failure'}]};self.assertFalse(successful(report));self.assertFalse(successful({'events':[],'errors':[]}))
 def test_input_is_not_mutated(self):
  r=empty();before=copy.deepcopy(r);classify_empty(r,'TBD vs TBD',META);self.assertEqual(r,before)
if __name__=='__main__': unittest.main()
