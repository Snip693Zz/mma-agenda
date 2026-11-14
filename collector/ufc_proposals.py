"""Propositions UFC : aucune écriture Supabase ou dans les données de secours."""
import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit

def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
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

def title_action(current, observed):
 if not isinstance(observed,str) or not observed.strip(): return 'keep'
 current=(current or '').strip();observed=observed.strip()
 if current==observed: return 'keep'
 def norm(value): return ' '.join(re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold()).split())
 old=norm(current);new=norm(observed)
 if old==new: return 'keep'
 header=re.fullmatch(r'(?:polymarket )?(ufc (?:[0-9]+|fight night))',new)
 if header and (old==header[1] or old.startswith(header[1]+' ')):
  return 'incomplete'
 if current.casefold() in observed.casefold(): return 'refine'
 return 'review'

def build(cards,baseline,catalog):
 result={'mode':'proposals_only','database_writes':False,'database_read':False,'fallback_writes':False,'automatic_publication':False,'baseline_source':'mma-data.json, pas la base Supabase en direct','baseline_sha256':digest(baseline),'cards_generated_at':cards.get('generated_at'),'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'entries':[],'errors':copy.deepcopy(cards.get('errors',[]))}
 known={};metadata={}
 for event in baseline['events']:
  if event.get('org')!='UFC': continue
  for address in {canonical(event.get('url')),canonical(event.get('officialCardUrl'))}-{None}: known.setdefault(address,[]).append(event)
 for group in catalog.get('events',[]):
  for item in group.get('observations',[group]):
   address=canonical(item.get('source_url'))
   if address and item.get('source_kind')=='official' and item.get('method')=='ufc_hero_timestamp':
    metadata.setdefault(address,{})[digest(item)]=item
 counts=collections.Counter(canonical(e.get('source_url')) for e in cards.get('events',[]))
 for observed in cards.get('events',[]):
  address=canonical(observed.get('source_url'))
  entry={'source_url':address or observed.get('source_url'),'type':'blocked','requires_review':True,'ready_to_publish':False,'deletions_allowed':False}
  result['entries'].append(entry)
  if not address or counts[address]!=1 or len(known.get(address,[]))>1:
   entry['reason']='URL invalide ou rapprochement ambigu';continue
  previous=known.get(address,[None])[0]
  if previous: entry['existing_id']=previous['id'];entry['existing_sha256']=digest(previous)
  if observed.get('status')=='pending_card':
   if previous and any(c.get('fights') for c in previous.get('cards',[])): entry['reason']='Combats existants absents du relevé';continue
   entry['type']='watch_only';entry['reason']='Carte en attente, aucune création ou suppression proposée';continue
  if observed.get('status')!='parsed' or observed.get('issues'):
   entry['reason']='Extraction non validée';continue
  try:
   new={}
   for fight in observed.get('fights',[]):
    if fight.get('source_kind')!='official' or canonical(fight.get('source_url'))!=address: raise ValueError('Provenance incohérente')
    new[pair_key(fight['fighters'])]=fight['fighters']
   if not new: raise ValueError('Aucun combat exploitable')
   old={pair_key(pair):pair for c in previous.get('cards',[]) for pair in c.get('fights',[])} if previous else {}
  except (KeyError,TypeError,ValueError) as error:
   entry['reason']=str(error);continue
  added=[new[k] for k in sorted(new.keys()-old.keys())];missing=[old[k] for k in sorted(old.keys()-new.keys())]
  entry['observed_fights']=list(new.values());entry['new_pairs']=added;entry['existing_not_observed']=missing;entry['coverage']='partial'
  if previous:
   entry['preserve_existing_cards']=True
   metas=list(metadata.get(address,{}).values())
   meta=metas[0] if len(metas)==1 else None
   date_change=bool(meta and isinstance(meta.get('date'),str) and meta['date'].strip() and meta['date'].strip()!=previous.get('date'))
   if missing or date_change:
    entry['type']='review_discrepancy'
    if date_change and not missing: entry['reason']='Changement de date à valider'
    continue
   updates=[]
   if meta:
    title=meta.get('title');place=meta.get('place')
    action=title_action(previous.get('title'),title)
    entry['title_comparison']={'action':action,'existing_title':previous.get('title'),'observed_title':title}
    if action=='review':
     entry['type']='review_discrepancy';entry['reason']='Changement de titre non confirmé';continue
    if action=='refine':
     updates.append({'field':'title','current_value':previous.get('title'),'proposed_value':title.strip()})
    if isinstance(place,str) and place.strip() and place.strip()!=previous.get('place'):
     updates.append({'field':'place','current_value':previous.get('place'),'proposed_value':place.strip()})
   if added:
    entry['type']='add_fights_proposal'
    continue
   if updates:
    entry['type']='update_event_proposal'
    entry['updates']=updates
    entry['metadata_evidence']=copy.deepcopy(meta)
    entry['checks_before_publication']=['Relire les données Supabase actuelles','Confirmer le titre ou le lieu sur la fiche officielle','Valider explicitement le lot']
    continue
   entry['type']='unchanged'
   continue
  metas=list(metadata.get(address,{}).values())
  if len(metas)!=1:
   entry['reason']='Métadonnées officielles absentes ou ambiguës';continue
  meta=metas[0];date=meta.get('date')
  try:
   if not isinstance(date,str) or dt.date.fromisoformat(date).isoformat()!=date: raise ValueError()
  except ValueError:
   entry['reason']='Date officielle non établie';continue
  proposed_id='ufc-auto-'+hashlib.sha256(address.encode()).hexdigest()[:12]
  if any(e['id']==proposed_id for e in baseline['events']):
   entry['reason']='Identifiant proposé déjà utilisé';continue
  entry['type']='create_event_proposal'
  entry['metadata_evidence']=copy.deepcopy(meta)
  entry['checks_before_publication']=['Relire les données Supabase actuelles','Confirmer ou compléter le lieu et le titre','Vérifier les cartes et leurs horaires sans utiliser l’heure d’en-tête par défaut','Valider explicitement le lot']
  entry['draft_event']={'id':proposed_id,'org':'UFC','title':meta.get('title') or 'UFC','date':date,'place':meta.get('place') or 'Lieu à confirmer','official':False,'url':address,'officialCardUrl':address,'note':'Combats issus de la fiche officielle UFC. Répartition et horaires des cartes à confirmer ; aucun palmarès ajouté.','cards':[{'name':'Combats officiels — répartition à confirmer','start':None,'level':'official','source':address,'fights':list(new.values())}]}
 result['summary']=dict(collections.Counter(e['type'] for e in result['entries']))
 return result

def live(baseline):
 try:
  from .ufc_cards_review import collect_reviewed
  from .discover import Client
  from .v2 import ufc_html
 except ImportError:
  from ufc_cards_review import collect_reviewed
  from discover import Client
  from v2 import ufc_html
 cards=collect_reviewed(baseline);catalog={'events':[]};client=None
 today=dt.datetime.now(dt.timezone.utc).date().isoformat()
 for event in cards['events']:
  if event['status']!='parsed': continue
  try:
   if client is None: client=Client('https://www.ufc.com/events')
   metadata,issues,_=ufc_html(client.get(event['source_url']),event['source_url'],today)
   catalog['events'].extend(metadata)
   if issues: cards['errors'].extend(issues)
  except Exception as error: cards['errors'].append({'source':event['source_url'],'phase':'metadata','reason':str(error)})
 return cards,catalog

def main():
 p=argparse.ArgumentParser();p.add_argument('--baseline',default='mma-data.json');p.add_argument('--cards');p.add_argument('--catalog');p.add_argument('--output',default='reports/ufc-proposals.json');a=p.parse_args()
 if bool(a.cards)!=bool(a.catalog): p.error('cards et catalog doivent être fournis ensemble')
 if Path(a.output).resolve() in {Path(x).resolve() for x in (a.baseline,a.cards,a.catalog) if x}: p.error('Le rapport ne doit remplacer aucune source')
 baseline=json.loads(Path(a.baseline).read_text(encoding='utf-8'))
 cards,catalog=(json.loads(Path(a.cards).read_text(encoding='utf-8')),json.loads(Path(a.catalog).read_text(encoding='utf-8'))) if a.cards else live(baseline)
 result=build(cards,baseline,catalog);target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result['summary']))
 return 2 if result['errors'] or not result['entries'] or any(e['type']=='blocked' for e in result['entries']) else 0
if __name__=='__main__': raise SystemExit(main())
