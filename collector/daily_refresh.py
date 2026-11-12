"""Rapprochement quotidien UFC : lecture Supabase, propositions et publication sûre."""
import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit

def sha(value): return hashlib.sha256(value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def canonical(value):
 try:
  p=urlsplit(value or '')
  if p.scheme!='https' or p.hostname not in ('ufc.com','www.ufc.com') or p.username or p.password or p.port not in (None,443) or not re.fullmatch(r'/event/[^/]+/?',p.path): return None
  return urlunsplit(('https','www.ufc.com',p.path.rstrip('/'),'',''))
 except (TypeError,ValueError): return None
def pair_key(pair):
 if not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(n,str) or not n.strip() for n in pair): raise ValueError('Paire invalide')
 def norm(n): return ' '.join(re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',n).encode('ascii','ignore').decode().casefold()).split())
 key=tuple(sorted(norm(n) for n in pair))
 if not all(key) or key[0]==key[1]: raise ValueError('Combattants non distincts')
 return key

def supabase_client():
 from supabase import create_client
 url=os.environ.get('SUPABASE_URL');key=os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
 if not url or not key: raise RuntimeError('SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis')
 return create_client(url,key)

def load_live(client):
 events={};cards=collections.defaultdict(list);fights=collections.defaultdict(list)
 for row in client.table('events').select('*').execute().data: events[row['id']]={**row,'cards':[]}
 for row in client.table('event_cards').select('*').execute().data: cards[row['event_id']].append(row)
 for row in client.table('fights').select('*').execute().data: fights[(row['event_id'],row['card_position'])].append(row)
 for event in events.values():
  for card in sorted(cards.get(event['id'],[]),key=lambda c:c['position']):
   event['cards'].append({'position':card['position'],'name':card['name'],'start':card['start_at'],'level':card['level'],'source':card['source'],'fights':[f['fighters'] for f in sorted(fights.get((event['id'],card['position']),[]),key=lambda f:f['position'])]})
 return {'events':list(events.values()),'fighterRecords':{}}

def build(cards,live,catalog):
 result={'mode':'daily_refresh','database_read':True,'automatic_publication':True,'source_report':cards.get('generated_at'),'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'entries':[],'published':[],'errors':copy.deepcopy(cards.get('errors',[]))}
 known={};metadata={}
 for event in live['events']:
  for address in {canonical(event.get('url')),canonical(event.get('official_card_url'))}-{None}: known.setdefault(address,[]).append(event)
 for group in catalog.get('events',[]):
  for item in group.get('observations',[group]):
   address=canonical(item.get('source_url'))
   if address and item.get('source_kind')=='official' and item.get('method')=='ufc_hero_timestamp': metadata.setdefault(address,{})[sha(item)]=item
 counts=collections.Counter(canonical(e.get('source_url')) for e in cards.get('events',[]))
 for observed in cards.get('events',[]):
  address=canonical(observed.get('source_url'));entry={'source_url':address or observed.get('source_url'),'kind':'review_discrepancy','status':'blocked','auto_publishable':False,'deletions_allowed':False}
  result['entries'].append(entry)
  if not address or counts[address]!=1 or len(known.get(address,[]))>1: entry['reason']='URL invalide ou rapprochement ambigu';continue
  previous=known.get(address,[None])[0]
  if observed.get('status')=='pending_card':
   if previous and any(c.get('fights') for c in previous.get('cards',[])): entry['reason']='Combats existants absents du relevé';continue
   entry['kind']='watch_only';entry['status']='pending';entry['reason']='Carte en attente';continue
  if observed.get('status')!='parsed' or observed.get('issues'): entry['reason']='Extraction non validée';continue
  try:
   new={}
   for fight in observed.get('fights',[]):
    if fight.get('source_kind')!='official' or canonical(fight.get('source_url'))!=address: raise ValueError('Provenance incohérente')
    new[pair_key(fight['fighters'])]=fight['fighters']
   if not new: raise ValueError('Aucun combat exploitable')
   old={pair_key(pair):pair for c in previous.get('cards',[]) for pair in c.get('fights',[])} if previous else {}
  except (KeyError,TypeError,ValueError) as error: entry['reason']=str(error);continue
  added=[new[k] for k in sorted(new.keys()-old.keys())];missing=[old[k] for k in sorted(old.keys()-new.keys())]
  entry['observed_fights']=list(new.values());entry['new_pairs']=added;entry['existing_not_observed']=missing
  if previous:
   entry['kind']='review_discrepancy' if missing else 'add_fight' if added else 'watch_only'
   entry['status']='blocked' if missing else 'auto_publishable' if added else 'pending'
   entry['event_id']=previous['id'];entry['auto_publishable']=bool(added) and not missing
   if added: entry['payload']={'event_id':previous['id'],'card_position':0,'fights':added}
   continue
  metas=list(metadata.get(address,{}).values())
  if len(metas)!=1: entry['reason']='Métadonnées officielles absentes ou ambiguës';continue
  meta=metas[0];date=meta.get('date')
  try:
   if not isinstance(date,str) or dt.date.fromisoformat(date).isoformat()!=date: raise ValueError()
  except ValueError: entry['reason']='Date officielle non établie';continue
  proposed='ufc-auto-'+hashlib.sha256(address.encode()).hexdigest()[:12]
  if proposed in {e['id'] for e in live['events']}: entry['reason']='Identifiant déjà utilisé';continue
  entry['kind']='create_event';entry['status']='auto_publishable';entry['auto_publishable']=True;entry['metadata_evidence']=copy.deepcopy(meta)
  entry['payload']={'event':{'id':proposed,'org':'UFC','title':meta.get('title') or 'UFC','date':date,'place':meta.get('place') or 'Lieu à confirmer','official':False,'url':address,'official_card_url':address,'note':'Combats issus de la fiche officielle UFC. Répartition et horaires des cartes à confirmer ; aucun palmarès ajouté.','verified':dt.date.today().isoformat(),'extra':{'source_report':cards.get('generated_at'),'event_hero_start_at_paris':meta.get('start_at_paris'),'event_hero_role':'non attribué à une carte'}},'card':{'position':0,'name':'Combats officiels — répartition à confirmer','start':None,'level':'official','source':address,'fights':list(new.values())}}
 result['summary']=dict(collections.Counter(e['kind'] for e in result['entries']))
 return result

def publish(client,result):
 for entry in result['entries']:
  if entry.get('status')!='auto_publishable': continue
  payload=entry['payload']
  if entry['kind']=='create_event':
   event=payload['event'];card=payload['card']
   client.table('events').upsert(event).execute();client.table('event_cards').upsert({'event_id':event['id'],'position':card['position'],'name':card['name'],'start_at':card['start'],'level':card['level'],'source':card['source'],'extra':{'allocation':'unassigned','order_note':card.get('order_note','')}}).execute()
   for position,pair in enumerate(card['fights']):client.table('fights').upsert({'event_id':event['id'],'card_position':0,'position':position,'fighter_a':pair[0],'fighter_b':pair[1]}).execute()
  elif entry['kind']=='add_fight':
   event_id=payload['event_id'];existing=client.table('fights').select('position').eq('event_id',event_id).eq('card_position',0).execute().data
   start=max([r['position'] for r in existing],default=-1)+1
   for offset,pair in enumerate(payload['fights']):client.table('fights').upsert({'event_id':event_id,'card_position':0,'position':start+offset,'fighter_a':pair[0],'fighter_b':pair[1]}).execute()
  entry['status']='published';result['published'].append({'kind':entry['kind'],'source_url':entry['source_url'],'event_id':entry.get('event_id'),'fights':entry.get('new_pairs',[])})
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--cards');p.add_argument('--catalog');p.add_argument('--output',default='reports/daily-refresh.json');p.add_argument('--apply',action='store_true');a=p.parse_args()
 if bool(a.cards)!=bool(a.catalog): p.error('cards et catalog doivent être fournis ensemble')
 if Path(a.output).resolve() in {Path(x).resolve() for x in (a.cards,a.catalog) if x}: p.error('Le rapport ne doit remplacer aucune source')
 cards=json.loads(Path(a.cards).read_text()) if a.cards else None;catalog=json.loads(Path(a.catalog).read_text()) if a.catalog else None
 client=supabase_client();live=load_live(client)
 if cards is None:
  from ufc_cards_review import collect_reviewed
  from discover import Client
  from v2 import ufc_html
  cards=collect_reviewed(live);catalog={'events':[]};http=None;today=dt.datetime.now(dt.timezone.utc).date().isoformat()
  for event in cards['events']:
   if event['status']!='parsed':continue
   try:
    if http is None:http=Client('https://www.ufc.com/events')
    metadata,issues,_=ufc_html(http.get(event['source_url']),event['source_url'],today);catalog['events'].extend(metadata)
    if issues:cards['errors'].extend(issues)
   except Exception as error:cards['errors'].append({'source':event['source_url'],'phase':'metadata','reason':str(error)})
 result=build(cards,live,catalog)
 if a.apply:result=publish(client,result)
 target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'summary':result['summary'],'published':result['published'],'errors':result['errors']}))
 return 2 if result['errors'] or any(e['status']=='blocked' for e in result['entries']) else 0
if __name__=='__main__':raise SystemExit(main())
