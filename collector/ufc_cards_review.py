"""Réévalue uniquement les fiches sans combat, sans écrire dans l'agenda."""
import argparse
import copy
import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

class Signals(HTMLParser):
 def __init__(self,html):
  super().__init__(convert_charrefs=True);self.hidden=0;self.visible=[];self.athletes=False;self.structured_fighters=False;self.feed(html)
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ('script','style'): self.hidden+=1
  if tag=='a' and urlsplit(attrs.get('href','')).path.startswith('/athlete/'): self.athletes=True
 def handle_endtag(self,tag):
  if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
 def handle_data(self,value):
  if self.hidden:
   if re.search(r'"(?:competitor|athlete|homeTeam|awayTeam)"\s*:',value): self.structured_fighters=True
  else: self.visible.append(value)

def classify_empty(result,html,metadata):
 out=copy.deepcopy(result)
 if out.get('status')!='needs_review' or out.get('fights') or out.get('html_rows')!=0 or out.get('issues'): return out
 if out.get('comparison',{}).get('baseline_count',0)>0:
  out['pending_check']='Previously known fights absent: keep review status';return out
 signals=Signals(html)
 marker=bool(re.search(r'\bTBD\s+vs\.?\s+TBD\b',' '.join(signals.visible),re.I))
 identity=len(metadata)==1 and metadata[0].get('source_url')==out['source_url'] and metadata[0].get('source_kind')=='official' and metadata[0].get('method')=='ufc_hero_timestamp'
 if marker and identity and not signals.athletes and not signals.structured_fighters:
  out['status']='pending_card'
  out['pending_evidence']={'visible_placeholder':'TBD vs TBD','event_metadata_checked':True,'athlete_links_found':False,'structured_fighter_fields_found':False}
  out['card_empty_confirmed']=False
  out['pending_meaning']='Affiche non renseignée et aucun combat extrait ; réexaminer au prochain lancement, sans conclure à une carte définitivement vide.'
 else:
  out['pending_check']={'placeholder':marker,'metadata_valid':identity,'athlete_links':signals.athletes,'structured_fighter_fields':signals.structured_fighters}
 return out

def collect_reviewed(seed):
 try:
  from .ufc_cards import collect
  from .discover import Client
  from .v2 import ufc_html
 except ImportError:
  from ufc_cards import collect
  from discover import Client
  from v2 import ufc_html
 report=collect(seed);report['schema_version']=2;client=None
 today=dt.datetime.now(dt.timezone.utc).date().isoformat()
 for index,item in enumerate(report['events']):
  if item.get('status')!='needs_review' or item.get('html_rows')!=0 or item.get('fights') or item.get('comparison',{}).get('baseline_count',0)>0: continue
  try:
   if client is None: client=Client('https://www.ufc.com/events')
   html=client.get(item['source_url'])
   metadata,issues,_=ufc_html(html,item['source_url'],today)
   report['events'][index]=classify_empty(item,html,metadata if not issues else [])
  except Exception as error: report['errors'].append({'source':item['source_url'],'phase':'pending_card_check','reason':str(error)})
 report['summary']={'parsed':sum(e['status']=='parsed' for e in report['events']),'pending_card':sum(e['status']=='pending_card' for e in report['events']),'needs_review':sum(e['status']=='needs_review' for e in report['events']),'fights':sum(len(e['fights']) for e in report['events']),'errors':len(report['errors'])}
 return report

def successful(report):
 return bool(report['events']) and not report['errors'] and all(e['status'] in ('parsed','pending_card') for e in report['events'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--baseline',default='mma-data.json');p.add_argument('--output',default='reports/ufc-cards.json');a=p.parse_args()
 if Path(a.baseline).resolve()==Path(a.output).resolve(): p.error('Le rapport ne doit pas remplacer la base')
 report=collect_reviewed(json.loads(Path(a.baseline).read_text(encoding='utf-8')))
 out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report['summary'],ensure_ascii=False))
 return 0 if successful(report) else 2
if __name__=='__main__': raise SystemExit(main())
