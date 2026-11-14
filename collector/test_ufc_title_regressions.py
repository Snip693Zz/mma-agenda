import copy
import unittest
from collector.ufc_proposals import build, title_action
URL='https://www.ufc.com/event/example'
def case(old,new,added=False,date='2027-01-01',missing=False,place=None):
 b={'events':[{'id':'e','org':'UFC','url':URL,'title':old,'date':'2027-01-01','place':'Paris','cards':[{'fights':[['A','B']]+([['C','D']] if missing else [])}]}]}
 pairs=[['A','B']]+([['E','F']] if added else [])
 c={'events':[{'source_url':URL,'status':'parsed','issues':[],'fights':[{'fighters':p,'source_kind':'official','source_url':URL} for p in pairs]}],'errors':[]}
 m={'events':[{'source_url':URL,'source_kind':'official','method':'ufc_hero_timestamp','title':new,'date':date,'place':place}]}
 before=copy.deepcopy((b,c,m));entry=build(c,b,m)['entries'][0]
 assert (b,c,m)==before
 return entry
class TitleTests(unittest.TestCase):
 def test_five_reported_cases(self):
  for old,new in [('UFC Fight Night — Prochazka vs Stirling','UFC Fight Night'),('UFC 336 — Van vs Kape','UFC 336'),('UFC Fight Night — Adesanya vs Magomedov','UFC Fight Night'),('UFC 334 — Gane vs Hokit','Polymarket UFC 334'),('UFC 335 — Oliveira vs Lopes','UFC 335')]:
   with self.subTest(old=old):
    e=case(old,new);self.assertEqual(e['type'],'unchanged');self.assertEqual(e['title_comparison']['action'],'incomplete');self.assertNotIn('updates',e)
 def test_number_mismatch(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 335')['type'],'review_discrepancy')
 def test_number_prefix_not_same(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 33')['type'],'review_discrepancy')
 def test_different_matchup(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 336 — A vs C')['type'],'review_discrepancy')
 def test_unknown_sponsor_not_ignored(self):
  self.assertEqual(title_action('UFC 336 — A vs B','Unknown UFC 336'),'review')
 def test_date_still_blocks(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 336',date='2027-01-02')['type'],'review_discrepancy')
 def test_missing_fight_still_blocks(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 336',missing=True)['type'],'review_discrepancy')
 def test_addition_with_incomplete_title(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 336',added=True)['type'],'add_fights_proposal')
 def test_title_conflict_blocks_addition(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 335',added=True)['type'],'review_discrepancy')
 def test_place_update_preserves_title(self):
  e=case('UFC 336 — A vs B','UFC 336',place='Lyon');self.assertEqual(e['type'],'update_event_proposal');self.assertEqual([u['field'] for u in e['updates']],['place'])
 def test_refinement_matches_sql_rule(self):
  e=case('UFC 336','UFC 336 — A vs B');self.assertEqual(e['type'],'update_event_proposal')
  u=e['updates'][0];self.assertIn(u['current_value'].strip().lower(),u['proposed_value'].strip().lower())
 def test_formatting_only_preserved(self):
  self.assertEqual(case('UFC 336 — A vs B','UFC 336: A vs B')['type'],'unchanged')
if __name__=='__main__': unittest.main()
