"""Rapport V2 : soirées, observations de combats et rapprochements prudents."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin
from zoneinfo import ZoneInfo

PROMOTIONS = r'\b(?:UFC|PFL|ARES|HEXAGONE)\b'

def folded(value):
    value = unicodedata.normalize('NFKD', value or '')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', value.encode('ascii', 'ignore').decode().lower()).split())

def canonical(value):
    p = urlsplit(value or '')
    if p.scheme != 'https' or not p.hostname or p.username or p.password: return ''
    return urlunsplit(('https', p.hostname.removeprefix('www.'), p.path.rstrip('/'), '', ''))

def specific(value):
    return bool(re.search(r'/(?:event|events|evenement|evenements)/[^/]+$', urlsplit(value or '').path.rstrip('/')))

def matches(item, baseline):
    exact, probable = [], []
    identity = canonical(item.get('event_url'))
    a = folded(item.get('title'))
    for old in baseline:
        if old.get('org') != item.get('org'): continue
        if identity and specific(identity) and identity in {canonical(old.get('url')), canonical(old.get('officialCardUrl')), canonical(old.get('boxUrl'))}:
            exact.append(old)
        elif item.get('date') == old.get('date'):
            b = folded(old.get('title'))
            n = re.search(r'\b(?:ufc|ares|hexagone mma)\s+(\d+)\b', a)
            m = re.search(r'\b(?:ufc|ares|hexagone mma)\s+(\d+)\b', b)
            generic = a in ('ufc', 'pfl', 'ares', 'hexagone', 'hexagone mma')
            prefix = not generic and len(a.split()) >= 2 and (b.startswith(a + ' ') or a.startswith(b + ' ') or a == b)
            if (n and m and n[1] == m[1]) or prefix: probable.append(old)
    return exact or probable

class Node:
    def __init__(self, tag='', attrs=None): self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def nodes(self):
        yield self
        for c in self.children:
            if isinstance(c, Node): yield from c.nodes()
    def text(self):
        if self.tag in ('script', 'style'): return ''
        return ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)

class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'): self.stack.append(n)
    def handle_startendtag(self, tag, attrs): self.stack[-1].children.append(Node(tag, attrs))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, value): self.stack[-1].children.append(value)

def ufc_html(html, address, today):
    tree = Tree(html).root
    if not re.fullmatch(r'/event/[^/]+/?', urlsplit(address).path):
        sections = [n for n in tree.nodes() if n.attrs.get('id') == 'events-list-upcoming']
        links = []
        for section in sections:
            for n in section.nodes():
                absolute = urljoin(address, n.attrs.get('href', ''))
                if n.tag == 'a' and urlsplit(absolute).hostname == urlsplit(address).hostname and re.fullmatch(r'/event/[^/]+/?', urlsplit(absolute).path):
                    if absolute not in links: links.append(absolute)
        return [], [], links
    titles = [n.text().strip() for n in tree.nodes() if n.tag == 'h1' and re.search(r'\bUFC\b', n.text(), re.I)]
    values = set()
    for bottom in tree.nodes():
        if 'c-hero__bottom-text' not in bottom.attrs.get('class', '').split(): continue
        for n in bottom.nodes():
            raw = n.attrs.get('data-timestamp', '')
            if not re.fullmatch(r'\d{10}|\d{13}', raw): continue
            instant = dt.datetime.fromtimestamp(int(raw) / (1000 if len(raw)==13 else 1), dt.timezone.utc)
            shown = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})\s*/\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s+(EST|EDT)\b', n.text(), re.I)
            if not shown: continue
            offset = -5 if shown[6].upper() == 'EST' else -4
            local = instant.astimezone(dt.timezone(dt.timedelta(hours=offset)))
            month = 'jan feb mar apr may jun jul aug sep oct nov dec'.split().index(shown[1].lower())+1
            hour = int(shown[3]) % 12 + (12 if shown[5].upper() == 'PM' else 0)
            if 2000 <= local.year <= 2100 and (local.month, local.day, local.hour, local.minute) == (month, int(shown[2]), hour, int(shown[4])):
                values.add((instant.isoformat(), local.date().isoformat(), shown[6].upper()))
    if len(values) != 1 or not titles:
        return [], [{'source_url':address,'reason':'UFC : timestamp de la zone événement absent, ambigu ou incompatible avec la date affichée'}], []
    instant, date, zone = next(iter(values))
    if date < today: return [], [], []
    paris = dt.datetime.fromisoformat(instant).astimezone(ZoneInfo('Europe/Paris')).isoformat()
    return [{'org':'UFC','title':titles[0],'date':date,'place':None,'event_url':address,'source_url':address,'source_kind':'official','method':'ufc_hero_timestamp','raw_date':instant,'start_at_utc':instant,'start_at_paris':paris,'date_display_timezone':zone,'time_role':'event_hero_not_assigned_to_a_card'}], [], []

def valid_date(value):
    try: return isinstance(value,str) and dt.date.fromisoformat(value).isoformat()==value
    except ValueError: return False

def refine(raw, baseline):
    report = {'schema_version':2,'mode':'dry_run','database_writes':False,'coverage':'partial','as_of':raw['as_of'],'sources':copy.deepcopy(raw.get('sources',[])),'events':[],'bout_observations':[],'review':[],'not_implemented':['Publication et écriture Supabase','Validation et affectation automatique des cartes','Palmarès','Adaptateurs Sherdog et Tapology']}
    observations, fights = [], []
    for item in raw.get('candidates',[]) + raw.get('review',[]):
        item = copy.deepcopy(item)
        name = item.get('title','')
        if re.search(r'\s+vs\.?\s+', name, re.I) and not re.search(PROMOTIONS, name, re.I):
            fights.append(item)
        elif item.get('org') and valid_date(item.get('date')) and re.search(PROMOTIONS,name,re.I):
            observations.append(item)
        else: report['review'].append(item)
    groups = {}
    for item in observations:
        linked = matches(item, baseline)
        same = linked[0] if len(linked)==1 else None
        identity = canonical(item.get('event_url'))
        key = ('existing',same['id']) if same else ('url',item['org'],identity) if identity and specific(identity) else ('listing',item['org'],item['date'],folded(item['title']),folded(item.get('place')))
        if key not in groups:
            uid = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
            groups[key] = {'candidate_id':uid,'org':item['org'],'date':item['date'],'display_title':same.get('title') if same else item['title'],'display_place':same.get('place') if same else item.get('place'),'existing_ids':[e['id'] for e in linked],'proposal':'existing_review_only' if same else 'ambiguous_existing' if linked else 'new_candidate','observations':[],'conflicts':[],'automatic_changes':False}
        group = groups[key]
        clean = {k:v for k,v in item.items() if k not in ('differences','possible_existing_ids','proposal','status')}
        if clean not in group['observations']: group['observations'].append(clean)
        dates = sorted({o['date'] for o in group['observations']} | ({same['date']} if same else set()))
        group['conflicts'] = [{'field':'date','values':dates}] if len(dates)>1 else []
        if group['conflicts']: group['proposal'] = 'conflict_review_only'
        if same:
            group['retained_existing'] = {k:copy.deepcopy(same[k]) for k in ('id','title','place','date','cards') if k in same}
    report['events'] = sorted(groups.values(),key=lambda g:(g['date'],g['org'],g['candidate_id']))
    for fight in fights:
        page = canonical(fight.get('source_url'))
        parents = [g for g in report['events'] if any(canonical(o.get('source_url'))==page and (not fight.get('org') or o['org']==fight['org']) for o in g['observations'])]
        observation = {k:v for k,v in fight.items() if k not in ('differences','possible_existing_ids','proposal','status','reason')}
        observation['parent_candidate_ids'] = [g['candidate_id'] for g in parents]
        observation['association'] = 'page_parent_review_only' if len(parents)==1 else 'ambiguous_parent'
        observation['source_kind'] = fight.get('source_kind') or next((s.get('source_kind','secondary') for g in parents for s in g['observations'] if canonical(s.get('source_url'))==page),'secondary')
        report['bout_observations'].append(observation)
    report['summary'] = {'raw_candidates':len(raw.get('candidates',[])),'event_groups':len(report['events']),'new_candidates':sum(g['proposal']=='new_candidate' for g in report['events']),'existing_groups':sum(g['proposal']=='existing_review_only' for g in report['events']),'bout_observations':len(report['bout_observations']),'review_items':len(report['review']),'conflicted_groups':sum(bool(g['conflicts']) for g in report['events'])}
    return report

def collect(baseline, today, limit):
    try:
        from . import discover as core
    except ImportError:
        import discover as core
    raw = {'as_of':today,'sources':[],'candidates':[],'review':[]}
    for org, kind, address in core.SOURCES:
        source = {'org':org,'url':address,'status':'pending','pages_read':0,'errors':[],'coverage':'partial'}
        raw['sources'].append(source)
        try:
            client = core.Client(address)
            html = client.get(address)
            source['pages_read'] += 1
            found, review, links = core.parse_page(html,org,kind,address,today)
            if org=='UFC':
                extra, uncertain, upcoming = ufc_html(html,address,today)
                found.extend(extra); review.extend(uncertain)
                if upcoming: links = upcoming
            source['detail_links_found'] = len(links)
            source['detail_limit'] = limit
            source['unvisited_detail_links'] = max(0,len(links)-limit)
            for detail in links[:limit]:
                try:
                    html = client.get(detail)
                    source['pages_read'] += 1
                    more, uncertain, _ = core.parse_page(html,org,kind,detail,today)
                    found.extend(more); review.extend(uncertain)
                    if org=='UFC':
                        extra, uncertain, _ = ufc_html(html,detail,today)
                        found.extend(extra); review.extend(uncertain)
                except Exception as error: source['errors'].append({'url':detail,'reason':str(error)})
            raw['candidates'].extend(found); raw['review'].extend(review)
            source['status'] = 'observations_found' if found else 'needs_adapter_or_review'
        except Exception as error:
            source['status'] = 'unavailable_or_disallowed'
            source['errors'].append({'url':address,'reason':str(error)})
    return refine(raw, baseline)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline',default='mma-data.json')
    parser.add_argument('--input',help='Rejouer un ancien rapport sans aucun accès réseau')
    parser.add_argument('--output',default='reports/discovery-v2.json')
    parser.add_argument('--detail-limit',type=int,default=12)
    parser.add_argument('--as-of',default=dt.datetime.now(ZoneInfo('Europe/Paris')).date().isoformat())
    args = parser.parse_args()
    if not 1 <= args.detail_limit <= 20: parser.error('detail-limit doit être compris entre 1 et 20')
    destination = Path(args.output)
    forbidden = {Path(args.baseline).resolve()} | ({Path(args.input).resolve()} if args.input else set())
    if destination.resolve() in forbidden: parser.error('Le rapport ne doit remplacer ni la base ni le rapport source')
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))['events']
    report = refine(json.loads(Path(args.input).read_text(encoding='utf-8')),baseline) if args.input else collect(baseline,dt.date.fromisoformat(args.as_of).isoformat(),args.detail_limit)
    report['generated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False))
    return 0 if report['events'] else 2

if __name__=='__main__': raise SystemExit(main())
