import copy
import unittest
from collector.ufc_cards import extract,compare,event_url
URL='https://www.ufc.com/event/test'
def row(a,b): return '<li class="c-listing-fight"><div class="c-listing-fight__corner-name"><span>'+a+'</span></div><div class="c-listing-fight__corner-name">'+b+'</div></li>'
class CardTests(unittest.TestCase):
 def test_extracts_names_without_a_hardcoded_list(self):
  r=extract(row('Fighter Alpha','Fighter Beta'),URL)
  self.assertEqual(r['status'],'parsed');self.assertEqual(r['fights'][0]['fighters'],['Fighter Alpha','Fighter Beta'])
 def test_twelve_fixture_rows_not_twelve_hardcoded_names(self):
  r=extract(''.join(row('Alpha '+str(i),'Beta '+str(i)) for i in range(12)),URL)
  self.assertEqual(len(r['fights']),12)
 def test_nested_name_and_unicode(self):
  r=extract(row('Benoît <b>Saint-Denis</b>','Quillan Salkilld'),URL)
  self.assertEqual(r['fights'][0]['fighters'][0],'Benoît Saint-Denis')
 def test_duplicate_mobile_markup_is_deduplicated(self):
  r=extract(row('Alpha','Beta')+row('Beta','Alpha'),URL)
  self.assertEqual(len(r['fights']),1)
 def test_incomplete_row_is_not_ignored_as_success(self):
  r=extract(row('Alpha','Beta')+row('Gamma','TBA'),URL)
  self.assertEqual(r['status'],'needs_review');self.assertEqual(len(r['issues']),1)
 def test_unknown_markup_is_not_an_empty_card_confirmation(self):
  self.assertEqual(extract('<h1>UFC</h1>',URL)['status'],'needs_review')
 def test_never_assigns_card_or_time(self):
  f=extract(row('Alpha','Beta'),URL)['fights'][0]
  self.assertIsNone(f['start_at']);self.assertEqual(f['allocation'],'unassigned')
 def test_missing_fight_is_only_a_review_item(self):
  baseline={'id':'test','cards':[{'fights':[['Alpha','Beta'],['Gamma','Delta']]}]};old=copy.deepcopy(baseline)
  c=compare(extract(row('Alpha','Beta'),URL),baseline)
  self.assertEqual(len(c['baseline_not_observed']),1);self.assertTrue(c['missing_pairs_are_not_cancellations']);self.assertFalse(c['automatic_changes']);self.assertEqual(baseline,old)
 def test_external_or_credential_urls_rejected(self):
  for u in ['https://evil.example/event/test','http://www.ufc.com/event/test','https://user@www.ufc.com/event/test','https://www.ufc.com/events']:
   self.assertIsNone(event_url(u))
 def test_script_text_is_not_a_fighter_name(self):
  r=extract(row('Alpha<script>intrusion</script>','Beta'),URL)
  self.assertEqual(r['fights'][0]['fighters'],['Alpha','Beta'])
if __name__=='__main__': unittest.main()
