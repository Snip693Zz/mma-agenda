"""Extraction UFC en mode rapport : aucune écriture dans la base ou les secours."""
import argparse
import datetime as dt
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

class Node:
 def __init__(self,tag='',attrs=()): self.tag,self.attrs,self.children=tag,dict(attrs),[]
 def nodes(self):
  yield self
  for c in self.children:
   if isinstance(c,Node): yield from c.nodes()
 def text(self):
  if self.tag in ('script','style'): return ''
  return ' '.join(c.text() if isinstance(c,Node) else c for c in self.children)
 def has(self,name): return name in self.attrs.get('class','').split()
class Tree(HTMLParser):
 def __init__(self,html):
  super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root];self.feed(html)
 def handle_starttag(self,tag,attrs):
  n=Node(tag,attrs);self.stack[-1].children.append(n)
  if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'): self.stack.append(n)
 def handle_startendtag(self,tag,attrs): self.stack[-1].children.append(Node(tag,attrs))
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==tag: del self.stack[i:];break
 def handle_data(self,value): self.stack[-1].children.append(value)
def folded(value):
 value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold()
 return ' '.join(re.sub(r'[^a-z0-9]+',' ',value).split())
def pair_key(pair): return tuple(sorted(folded(n) for n in pair))
def event_url(value):
 p=urlsplit(value)
 if p.scheme!='https' or p.hostname not in ('www.ufc.com','ufc.com') or p.username or p.password or p.port not in (None,443) or not re.fullmatch(r'/event/[^/]+/?',p.path): return None
 return urlunsplit(('https','www.ufc.com',p.path.rstrip('/'),'',''))
def extract(html,address):
 source=event_url(address)
 if not source: raise ValueError('Fiche UFC officielle attendue')
 tree=Tree(html).root;rows=[n for n in tree.nodes() if n.has('c-listing-fight')]
 fights=[];seen=set();issues=[]
 for index,row in enumerate(rows):
  names=[]
  for n in row.nodes():
   if n.has('c-listing-fight__corner-name'):
    value=' '.join(n.text().split())
    if value and value not in names: names.append(value)
  if len(names)!=2 or any(len(n)>160 or folded(n) in ('tba','tbd','to be announced','a determiner') for n in names) or pair_key(names)[0]==pair_key(names)[1]:
   issues.append({'row':index,'reason':'Deux noms distincts et complets non établis','names':names});continue
  key=pair_key(names)
  if key in seen: continue
  seen.add(key);fights.append({'fighters':names,'source_url':source,'source_kind':'official','allocation':'unassigned','start_at':None,'source_order':index})
 return {'source_url':source,'status':'parsed' if fights and not issues else 'needs_review','coverage':'partial','html_rows':len(rows),'fights':fights,'issues':issues,'cancellation_inference':False}
def compare(result,baseline):
 old={pair_key(pair):pair for card in baseline.get('cards',[]) for pair in card.get('fights',[])}
 new={pair_key(f['fighters']):f['fighters'] for f in result['fights']}
 return {'event_id':baseline['id'],'baseline_count':len(old),'observed_count':len(new),'matching_pairs':len(old.keys()&new.keys()),'observed_not_in_baseline':[new[k] for k in sorted(new.keys()-old.keys())],'baseline_not_observed':[old[k] for k in sorted(old.keys()-new.keys())],'missing_pairs_are_not_cancellations':True,'automatic_changes':False}
def collect(seed):
 try:
  from .discover import Client
 except ImportError:
  from discover import Client
 report={'mode':'dry_run','database_writes':False,'fallback_writes':False,'coverage':'partial','events':[],'errors':[],'not_implemented':['Répartition des cartes','Palmarès','Publication automatique'],'generated_at':dt.datetime.now(dt.timezone.utc).isoformat()}
 known={}
 for e in seed['events']:
  if e['org']=='UFC':
   address=event_url(e.get('officialCardUrl') or e['url'])
   if address: known[address]=e
 targets=list(known)
 try:
  client=Client('https://www.ufc.com/events')
  root=Tree(client.get('https://www.ufc.com/events')).root
  sections=[n for n in root.nodes() if n.attrs.get('id')=='events-list-upcoming']
  if not sections: report['errors'].append({'source':'catalogue UFC','reason':'Section des événements à venir non reconnue'})
  for section in sections:
   for n in section.nodes():
    if n.tag=='a':
     address=event_url(urljoin('https://www.ufc.com/events',n.attrs.get('href','')))
     if address and address not in targets: targets.append(address)
 except Exception as error:
  report['errors'].append({'source':'catalogue UFC','reason':str(error)})
  return report
 report['discovered_urls']=len(targets);report['unvisited_urls']=targets[12:]
 for address in targets[:12]:
  try:
   result=extract(client.get(address),address)
   if address in known: result['comparison']=compare(result,known[address])
   report['events'].append(result)
  except Exception as error: report['errors'].append({'source':address,'reason':str(error)})
 return report
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',default='mma-data.json');parser.add_argument('--output',default='reports/ufc-cards.json');args=parser.parse_args()
 if Path(args.output).resolve()==Path(args.baseline).resolve(): parser.error('Le rapport ne doit pas remplacer la base')
 report=collect(json.loads(Path(args.baseline).read_text(encoding='utf-8')))
 destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'events':[{'url':e['source_url'],'status':e['status'],'fights':len(e['fights'])} for e in report['events']],'errors':report['errors']},ensure_ascii=False))
 return 0 if report['events'] and not report['errors'] and all(e['status']=='parsed' for e in report['events']) else 2
if __name__=='__main__': raise SystemExit(main())
