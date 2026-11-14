import unittest
from collector.ufc_reconciliation_run import build_report, collect_details, run

URL='https://www.ufc.com/event/test'
HTML='<html>test</html>'
DETAILS={'status':'parsed','mode':'details_read_only','database_writes':False,'automatic_publication':False,'issues':[],'source_url':URL,'source_sha256':'a'*64,'event_patch':{'title':'UFC — Alpha vs Beta','place':'Arena','date':'2026-11-21'},'cards':[]}
BASELINE={'events':[{'id':'test','org':'UFC','url':URL,'officialCardUrl':URL,'date':'2026-11-21','title':'UFC','place':'À confirmer','cards':[{'position':0,'name':'Non attribués','start':None,'level':'official','source':URL,'extra':{'allocation':'unassigned'},'is_active':True,'fights':[['Alpha','Beta'],['Gamma','Delta']]}]}]}
CARDS={'generated_at':'2026-11-14T06:00:00Z','events':[{'status':'parsed','source_url':URL}],'errors':[]}

class RunnerTests(unittest.TestCase):
    def test_collect_details_uses_official_pages(self):
        details,errors=collect_details(CARDS,lambda address:HTML)
        self.assertEqual(list(details),[URL])
        self.assertEqual(details[URL]['status'],'parsed')
        self.assertEqual(errors,[])
    def test_build_report_accepts_dict_and_callable(self):
        for source in ({URL:HTML},lambda address:HTML):
            report=build_report(BASELINE,CARDS,source,extract=lambda html,address:DETAILS,reconciler=lambda baseline,details:{'mode':'ufc_daily_reconciliation','database_writes':False,'automatic_publication':False,'entries':[{'status':'reallocation_ready','issues':[]}],'errors':[]})
            self.assertEqual(report['entries'][0]['status'],'reallocation_ready')
            self.assertTrue(report['database_read'])
            self.assertFalse(report['database_writes'])
            self.assertFalse(report['automatic_publication'])
            self.assertFalse(report['entries'][0]['ready_to_publish'])
            self.assertNotIn('projected_event',report['entries'][0])
    def test_missing_page_is_reported_without_crash(self):
        details,errors=collect_details(CARDS,lambda address:None)
        self.assertEqual(details,{})
        self.assertEqual(errors[0]['phase'],'ufc_details')
    def test_invalid_page_is_reported_without_crash(self):
        def extract(html,address):
            raise ValueError('invalid')
        details,errors=collect_details(CARDS,lambda address:HTML,extract=extract)
        self.assertEqual(details,{})
        self.assertEqual(errors[0]['phase'],'ufc_details')
    def test_run_collects_errors_without_writes(self):
        class Client:
            baseline=BASELINE
            def get(self,address): return HTML
        report=run(Client(),lambda address:HTML,extract=lambda html,address:DETAILS,reconciler=lambda baseline,details:{'mode':'ufc_daily_reconciliation','database_writes':False,'automatic_publication':False,'entries':[{'status':'unchanged','issues':[]}],'errors':[]})
        self.assertEqual(report['entries'][0]['status'],'unchanged')
        self.assertTrue(report['database_read'])
        self.assertFalse(report['database_writes'])
        self.assertFalse(report['automatic_publication'])
        self.assertFalse(report['entries'][0]['ready_to_publish'])
    def test_run_records_details_failure_safely(self):
        class Client:
            baseline=BASELINE
            def get(self,address): return HTML
        def extract(html,address):
            raise RuntimeError('network')
        report=run(Client(),lambda address:HTML,extract=extract,reconciler=lambda baseline,details:{'mode':'ufc_daily_reconciliation','database_writes':False,'automatic_publication':False,'entries':[],'errors':[]})
        self.assertEqual(report['errors'][0]['phase'],'ufc_details')
        self.assertFalse(report['database_writes'])
    def test_run_records_baseline_failure_safely(self):
        class Failing:
            def get(self,address): return HTML
        report=run(Failing(),lambda address:HTML,extract=lambda html,address:DETAILS,reconciler=lambda baseline,details:{'entries':[],'errors':[]})
        self.assertEqual(report['errors'][0]['phase'],'supabase_read')
        self.assertFalse(report['database_writes'])

if __name__=='__main__':
    unittest.main()
