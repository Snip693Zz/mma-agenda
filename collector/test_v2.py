import copy
import datetime as dt
import json
import unittest
from collector.v2 import refine, ufc_html, matches

class V2Tests(unittest.TestCase):
    def item(self,title='PFL Dubai',date='2026-11-14',org='PFL',page='https://pflmma.com/event/dubai',kind='official'):
        return {'org':org,'title':title,'date':date,'place':None,'source_url':page,'event_url':page,'source_kind':kind,'raw_date':date}
    def raw(self,items,review=None): return {'as_of':'2026-11-12','candidates':items,'review':review or []}
    def test_bouts_are_not_events(self):
        r=refine(self.raw([self.item(),self.item('Patrick Habirora vs Omar El Dafrawy')]),[])
        self.assertEqual(r['summary']['event_groups'],1)
        self.assertEqual(r['summary']['bout_observations'],1)
        self.assertEqual(r['bout_observations'][0]['association'],'page_parent_review_only')
    def test_rich_title_and_cards_retained(self):
        base=[{'id':'dubai','org':'PFL','title':'PFL Dubaï — Nemkov vs Bilostenniy','date':'2026-11-14','place':'Coca-Cola Arena · Dubaï','url':'https://pflmma.com/event/dubai','cards':[{'name':'Carte principale','fights':[['A','B']]}]}]
        snapshot=copy.deepcopy(base)
        r=refine(self.raw([self.item(),self.item('A vs B')]),base)
        self.assertEqual(r['events'][0]['display_title'],base[0]['title'])
        self.assertEqual(r['events'][0]['retained_existing']['cards'],base[0]['cards'])
        self.assertEqual(base,snapshot)
        self.assertFalse(r['events'][0]['automatic_changes'])
    def test_same_day_different_events_stay_separate(self):
        r=refine(self.raw([self.item('PFL Dubai'),self.item('PFL Paris',page='https://pflmma.com/event/paris')]),[])
        self.assertEqual(len(r['events']),2)
    def test_shared_catalogue_is_not_event_identity(self):
        base=[{'id':'45','org':'ARES','date':'2026-11-20','title':'ARES 45','url':'https://www.aresfighting.com/fr/events/'}]
        candidate=self.item('ARES 46','2026-12-11','ARES','https://www.aresfighting.com/fr/events/')
        self.assertEqual(matches(candidate,base),[])
    def test_date_conflict_kept_for_review(self):
        base=[{'id':'d','org':'PFL','title':'PFL Dubai','date':'2026-11-14','url':'https://pflmma.com/event/dubai'}]
        r=refine(self.raw([self.item(date='2026-11-15')]),base)
        self.assertEqual(r['events'][0]['proposal'],'conflict_review_only')
    def test_secondary_bout_does_not_become_official(self):
        parent=self.item(page='https://boxemag.ouest-france.fr/evenement/pfl-dubai',kind='secondary')
        bout={'title':'A vs B','source_url':parent['source_url'],'raw_date':'2026-11-14'}
        r=refine(self.raw([parent],[bout]),[])
        self.assertEqual(r['bout_observations'][0]['source_kind'],'secondary')
    def test_ambiguous_parent_not_selected(self):
        r=refine(self.raw([self.item('PFL Dubai',page='https://pflmma.com/events'),self.item('PFL Dubai 2',page='https://pflmma.com/events'),self.item('A vs B',page='https://pflmma.com/events')]),[])
        self.assertEqual(r['bout_observations'][0]['association'],'ambiguous_parent')
    def test_missing_data_is_not_a_cancellation(self):
        r=refine(self.raw([]),[{'id':'x','org':'UFC','date':'2026-11-14','title':'UFC 334'}])
        self.assertEqual(r['events'],[])
        self.assertNotIn('deletions',r)
    def hero(self,timestamp=None,label='Sat, Nov 14 / 9:00 PM EST'):
        timestamp=timestamp or int(dt.datetime(2026,11,15,2,tzinfo=dt.timezone.utc).timestamp())
        return f'<h1>Polymarket UFC 334</h1><div class="c-hero__bottom-text"><div data-timestamp="{timestamp}">{label}</div></div>'
    def test_ufc_timestamp_crosses_paris_midnight(self):
        found,review,_=ufc_html(self.hero(),'https://www.ufc.com/event/ufc-334','2026-11-12')
        self.assertEqual(found[0]['date'],'2026-11-14')
        self.assertTrue(found[0]['start_at_paris'].startswith('2026-11-15T03:00'))
        self.assertEqual(review,[])
    def test_ufc_milliseconds(self):
        timestamp=int(dt.datetime(2026,11,15,2,tzinfo=dt.timezone.utc).timestamp())*1000
        self.assertEqual(len(ufc_html(self.hero(timestamp),'https://www.ufc.com/event/ufc-334','2026-11-12')[0]),1)
    def test_ufc_does_not_guess_year(self):
        found,review,_=ufc_html('<h1>UFC Test</h1><div>Sat, Jan 16 / 8:00 PM EST</div>','https://www.ufc.com/event/test','2026-11-12')
        self.assertEqual(found,[])
        self.assertEqual(len(review),1)
    def test_ufc_incompatible_timestamp_rejected(self):
        found,review,_=ufc_html(self.hero(label='Sat, Nov 14 / 8:00 PM EST'),'https://www.ufc.com/event/ufc-334','2026-11-12')
        self.assertEqual(found,[])
        self.assertEqual(len(review),1)
    def test_ufc_upcoming_links_only(self):
        html='<details id="events-list-upcoming"><a href="/event/next">Carte</a><a href="https://evil.example/event/x">Non</a></details><a href="/event/past">Passé</a>'
        self.assertEqual(ufc_html(html,'https://www.ufc.com/events','2026-11-12')[2],['https://www.ufc.com/event/next'])
    def test_input_report_is_not_modified(self):
        raw=self.raw([self.item(),self.item('A vs B')])
        before=json.dumps(raw,sort_keys=True)
        refine(raw,[])
        self.assertEqual(json.dumps(raw,sort_keys=True),before)

if __name__=='__main__': unittest.main()
