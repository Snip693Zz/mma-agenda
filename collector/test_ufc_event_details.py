import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collector.ufc_event_details import extract_details, main
URL='https://www.ufc.com/event/test'

def row(a='Alpha',b='Beta'):
    return f'<li class="c-listing-fight"><span class="c-listing-fight__corner-name">{a}</span><span class="c-listing-fight__corner-name">{b}</span></li>'

def page(extra='',stamp='1795284000',shown='Sat, Nov 21 / 1:00 PM',rows=None):
    return f'<link rel="canonical" href="{URL}"><div class="c-hero__headline-prefix">UFC Test</div><div class="c-hero__headline">Alpha vs Beta</div><div class="field--name-venue">Arena</div><div class="c-hero__bottom-text"><div data-timestamp="1795284000">Sat, Nov 21 / 1:00 PM EST</div></div><div id="main-card"><div class="c-event-fight-card-broadcaster__time" data-timestamp="{stamp}">{shown}</div>{row() if rows is None else rows}</div>'+extra

class DetailsTests(unittest.TestCase):
    def test_card_schema_and_utc(self):
        r=extract_details(page(),URL)
        self.assertEqual(r['status'],'parsed',r['issues'])
        self.assertEqual(r['cards'][0]['start'],'2026-11-21T18:00:00Z')
        self.assertEqual(set(r['cards'][0]),{'name','start','level','source','fights'})
        self.assertFalse(r['database_writes'])
        self.assertEqual(r['event_patch']['date'],'2026-11-21')
    def test_empty_early_prelims_ignored(self):
        r=extract_details(page('<div id="early-prelims">Early Prelims</div>'),URL)
        self.assertEqual(len(r['cards']),1)
    def test_ticket_timestamp_not_used(self):
        r=extract_details(page('<div class="c-listing-ticket__time" data-timestamp="1791450000">5:00 AM EDT</div>'),URL)
        self.assertEqual(r['status'],'parsed')
        self.assertEqual(r['cards'][0]['start'],'2026-11-21T18:00:00Z')
    def test_duplicate_fight_deduplicated(self):
        r=extract_details(page(rows=row()+row('Beta','Alpha')),URL)
        self.assertEqual(r['cards'][0]['fights'],[['Alpha','Beta']])
    def test_unknown_names_are_not_hardcoded(self):
        r=extract_details(page(rows=row('Benoît Test','Gamma Example')),URL)
        self.assertEqual(r['status'],'parsed')
    def test_incompatible_time_blocks_entire_patch(self):
        r=extract_details(page(shown='Sat, Nov 21 / 2:00 PM'),URL)
        self.assertEqual(r['status'],'needs_review')
        self.assertEqual(r['cards'],[])
        self.assertEqual(r['event_patch'],{})
    def test_cross_card_duplicate_blocked(self):
        r=extract_details(page('<div id="prelims-card">'+row()+'</div>'),URL)
        self.assertEqual(r['status'],'needs_review')
    def test_external_url_rejected(self):
        self.assertEqual(extract_details(page(),'https://evil.example/event/test')['status'],'needs_review')
    def test_fight_outside_sections_blocked(self):
        self.assertEqual(extract_details(page(row('Gamma','Delta')),URL)['status'],'needs_review')
    def test_missing_time_kept_unknown(self):
        html=page().replace('class="c-event-fight-card-broadcaster__time"','class="unknown"')
        r=extract_details(html,URL)
        self.assertEqual(r['status'],'parsed')
        self.assertIsNone(r['cards'][0]['start'])
    def test_cli_preserves_source_hash_for_all_newlines(self):
        for newline in ('\n','\r\n','\r'):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'source.html'
                output=Path(directory)/'reports'/'details.json'
                raw=(page().replace('><','>'+newline+'<')+newline).encode('utf-8')
                source.write_bytes(raw)
                with patch('sys.argv',['ufc_event_details','--html',str(source),'--url',URL,'--output',str(output)]):
                    self.assertEqual(main(),0)
                report=json.loads(output.read_text(encoding='utf-8'))
                self.assertEqual(report['source_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(source.read_bytes(),raw)

if __name__=='__main__':
    unittest.main()
