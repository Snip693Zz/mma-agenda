"""Extraction des détails UFC, sans publication. Les horaires sont ceux des cartes."""
import argparse
import datetime as dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
try:
    from .ufc_details_probe import Tree
except ImportError:
    from ufc_details_probe import Tree

SECTIONS = [('early-prelims','Premiers préliminaires'),('prelims-card','Préliminaires'),('main-card','Carte principale')]

def has(node, cls):
    return cls in node.attrs.get('class','').split()

def unique(values):
    values = set(values)
    if len(values) != 1:
        raise ValueError('Valeur absente ou ambiguë')
    return next(iter(values))

def instant(node):
    raw = node.attrs.get('data-timestamp','')
    if not re.fullmatch(r'\d{10}|\d{13}',raw):
        raise ValueError('Horodatage absent ou invalide')
    value = dt.datetime.fromtimestamp(int(raw)/(1000 if len(raw)==13 else 1),dt.timezone.utc)
    if not 2000 <= value.year <= 2100:
        raise ValueError('Année hors limites')
    local = value.astimezone(ZoneInfo('America/New_York'))
    text = node.text()
    clock = re.search(r'\b(\d{1,2}):(\d{2})\s*(AM|PM)\b',text,re.I)
    if not clock or not 1 <= int(clock[1]) <= 12 or int(clock[2]) > 59:
        raise ValueError('Heure affichée invalide')
    hour = int(clock[1])%12+(12 if clock[3].upper()=='PM' else 0)
    if (local.hour,local.minute)!=(hour,int(clock[2])):
        raise ValueError('Heure affichée incompatible')
    zone = re.search(r'\b(EST|EDT)\b',text)
    if zone and zone[1] != local.tzname():
        raise ValueError('Fuseau affiché incompatible')
    day = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})',text)
    if day and (local.month,local.day)!=('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split().index(day[1])+1,int(day[2])):
        raise ValueError('Date affichée incompatible')
    return value.isoformat().replace('+00:00','Z')

def token(name):
    value = unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    return ' '.join(re.sub('[^a-z0-9]+',' ',value).split())

def extract_details(html, address):
    result = {'schema_version':1,'mode':'details_read_only','database_writes':False,'automatic_publication':False,'source_url':address,'source_sha256':hashlib.sha256(html.encode()).hexdigest(),'status':'needs_review','event_patch':{},'cards':[],'issues':[]}
    try:
        p = urlsplit(address)
        if p.scheme!='https' or p.hostname not in ('ufc.com','www.ufc.com') or p.username or p.password or p.port not in (None,443) or p.query or p.fragment or not re.fullmatch('/event/[a-zA-Z0-9-]+/?',p.path):
            raise ValueError('URL officielle UFC requise')
        nodes = list(Tree(html).root.nodes())
        canonical = [n.attrs.get('href') for n in nodes if n.tag=='link' and n.attrs.get('rel')=='canonical']
        expected = 'https://www.ufc.com'+p.path.rstrip('/')
        if unique(canonical) != expected:
            raise ValueError('Identité canonique non vérifiée')
        prefix = unique(n.text() for n in nodes if has(n,'c-hero__headline-prefix') and n.text())
        headline = unique(n.text() for n in nodes if has(n,'c-hero__headline') and n.text())
        if not re.match(r'^UFC\b',prefix) or token(headline) in ('tbd vs tbd','tba vs tba'):
            raise ValueError('Titre non exploitable')
        place = unique(n.text() for n in nodes if has(n,'field--name-venue') and n.text())
        hero = unique(instant(n) for parent in nodes if has(parent,'c-hero__bottom-text') for n in parent.nodes() if n.attrs.get('data-timestamp'))
        date = dt.datetime.fromisoformat(hero.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        result['event_patch'] = {'title':prefix+' — '+headline,'place':place,'date':date}
        seen = set()
        for section_id, name in SECTIONS:
            sections = [n for n in nodes if n.attrs.get('id')==section_id]
            if not sections:
                continue
            if len(sections)!=1:
                raise ValueError('Section de carte ambiguë')
            section = sections[0]
            children = list(section.nodes())
            fights = []
            local_seen = set()
            for row in children:
                if not has(row,'c-listing-fight'):
                    continue
                names = list(dict.fromkeys(n.text() for n in row.nodes() if has(n,'c-listing-fight__corner-name') and n.text()))
                keys = [token(n) for n in names]
                if len(names)!=2 or len(set(keys))!=2 or any(not k or k in ('tba','tbd','to be announced') for k in keys):
                    raise ValueError('Combat incomplet')
                key = tuple(sorted(keys))
                if key in local_seen:
                    continue
                if key in seen:
                    raise ValueError('Combat présent dans plusieurs cartes')
                local_seen.add(key)
                fights.append(names)
            times = [n for n in children if has(n,'c-event-fight-card-broadcaster__time')]
            if not fights and not times:
                continue
            start = unique(instant(n) for n in times) if times else None
            seen.update(local_seen)
            result['cards'].append({'name':name,'start':start,'level':'official','source':expected,'fights':fights})
        if not result['cards']:
            raise ValueError('Aucune carte exploitable')
        all_pairs = set()
        for row in nodes:
            if has(row,'c-listing-fight'):
                names = list(dict.fromkeys(n.text() for n in row.nodes() if has(n,'c-listing-fight__corner-name') and n.text()))
                if len(names)!=2:
                    raise ValueError('Combat hors carte ou incomplet')
                all_pairs.add(tuple(sorted(token(n) for n in names)))
        if all_pairs != seen:
            raise ValueError('Combats non rattachés à une carte')
        result['status'] = 'parsed'
    except (ValueError,TypeError,OverflowError,OSError) as error:
        result['issues'].append(str(error))
        result['event_patch'] = {}
        result['cards'] = []
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--html',required=True)
    parser.add_argument('--url',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    source, target = Path(args.html), Path(args.output)
    if target.resolve()==source.resolve() or 'reports' not in target.parts:
        parser.error('La sortie doit être un rapport distinct dans reports')
    report = extract_details(source.read_text(encoding='utf-8'),args.url)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['status']=='parsed' else 2

if __name__=='__main__':
    raise SystemExit(main())
