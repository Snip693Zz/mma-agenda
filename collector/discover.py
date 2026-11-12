"""Découverte MMA en lecture seule : rapport local, aucune écriture Supabase."""
import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse as url
import urllib.request as http
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

AGENT = 'MMAAgendaPersonalBot'
USER_AGENT = AGENT + '/0.1 (+https://github.com/Snip693Zz/mma-agenda)'
SOURCES = [
    ('UFC', 'official', 'https://www.ufc.com/events'),
    ('PFL', 'official', 'https://pflmma.com/events'),
    ('ARES', 'official', 'https://www.aresfighting.com/fr/events/'),
    ('HEXAGONE', 'official', 'https://hexagonemma.fr/evenements/'),
    (None, 'secondary', 'https://boxemag.ouest-france.fr/evenement/?discipline=mma'),
]

class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.structured = [], [], []
        self.hidden, self.script, self.ld, self.anchor = [], [], False, None
        self.feed(html)
        self.text = '\n'.join(x.strip() for x in ''.join(self.parts).splitlines() if x.strip())
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.hidden.append(tag)
            self.ld = tag == 'script' and a.get('type', '').lower() == 'application/ld+json'
            self.script = []
        if not self.hidden:
            if tag in ('div', 'p', 'li', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'br', 'time'):
                self.parts.append('\n')
            if tag == 'a':
                self.anchor = [a.get('href', ''), []]
    def handle_data(self, value):
        if self.hidden:
            if self.ld: self.script.append(value)
        else:
            self.parts.append(value)
            if self.anchor is not None: self.anchor[1].append(value)
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            if self.ld:
                try: self.structured.append(json.loads(''.join(self.script)))
                except (ValueError, TypeError): pass
            self.hidden.pop()
            self.ld = False
        if not self.hidden:
            if tag == 'a' and self.anchor is not None:
                self.links.append((self.anchor[0], ' '.join(self.anchor[1]).strip()))
                self.anchor = None
            if tag in ('div', 'p', 'li', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'time'):
                self.parts.append('\n')

class Redirect(http.HTTPRedirectHandler):
    def __init__(self, client): self.client = client
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        self.client.check_host(newurl)
        if self.client.rules is not None and not self.client.rules.can_fetch(AGENT, newurl):
            raise ValueError('Redirection interdite par robots.txt')
        return super().redirect_request(request, fp, code, msg, headers, newurl)

class Client:
    def __init__(self, root):
        self.host = url.urlsplit(root).hostname.removeprefix('www.')
        self.rules, self.last, self.delay = None, 0, 2.0
        self.opener = http.build_opener(Redirect(self))
        robot_url = url.urlunsplit(('https', url.urlsplit(root).netloc, '/robots.txt', '', ''))
        try: text = self.get(robot_url, check_rules=False)
        except urllib.error.HTTPError as e:
            if e.code != 404: raise
            text = ''
        self.rules = urllib.robotparser.RobotFileParser()
        self.rules.parse(text.splitlines())
        self.delay = max(2.0, self.rules.crawl_delay(AGENT) or 0)
        rate = self.rules.request_rate(AGENT)
        if rate and rate.requests: self.delay = max(self.delay, rate.seconds / rate.requests)
    def check_host(self, address):
        p = url.urlsplit(address)
        if p.scheme != 'https' or p.hostname is None or p.hostname.removeprefix('www.') != self.host or p.username or p.password or p.port not in (None, 443):
            raise ValueError('Adresse hors du domaine source autorisé')
    def get(self, address, check_rules=True):
        self.check_host(address)
        if check_rules and not self.rules.can_fetch(AGENT, address):
            raise ValueError('Accès interdit par robots.txt')
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        request = http.Request(address, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain,application/ld+json'})
        with self.opener.open(request, timeout=25) as response:
            self.check_host(response.url)
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ValueError('Page trop volumineuse')
            text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        if re.search(r'verify you are human|verify you.re human|access denied|just a moment', text[:5000], re.I):
            raise ValueError('Blocage ou vérification humaine : aucun contournement')
        return text

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)

def full_date(value):
    if not isinstance(value, str): return None
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.*)?', value):
        try: return dt.date.fromisoformat(value[:10]).isoformat()
        except ValueError: return None
    if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', value):
        try: return dt.datetime.strptime(value, '%d/%m/%Y').date().isoformat()
        except ValueError: return None
    return None

def organization(name):
    for token in ('UFC', 'PFL', 'ARES', 'HEXAGONE'):
        if re.search(r'\b' + token + r'\b', name, re.I): return token
    return None

def parse_page(html, org, kind, address, today):
    page = Page(html)
    found, review = [], []
    def add(name, raw_date, method, place=None, event_url=None):
        date = full_date(raw_date)
        promotion = org or organization(name)
        if not date or not promotion:
            review.append({'title': name, 'raw_date': raw_date, 'reason': 'Date complète ou organisation non établie', 'source_url': address})
            return
        if date < today: return
        found.append({'org': promotion, 'title': name.strip(), 'date': date, 'place': place, 'source_url': address, 'event_url': event_url, 'source_kind': kind, 'method': method, 'raw_date': raw_date, 'status': 'review_only'})
    for doc in page.structured:
        for item in walk(doc):
            types = item.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list) or not any(t in ('Event', 'SportsEvent') for t in types): continue
            name = item.get('name')
            if not isinstance(name, str): continue
            location = item.get('location')
            place = location.get('name') if isinstance(location, dict) else location if isinstance(location, str) else None
            raw_url = item.get('url')
            event_url = url.urljoin(address, raw_url) if isinstance(raw_url, str) else None
            if event_url and url.urlsplit(event_url).hostname != url.urlsplit(address).hostname: event_url = None
            add(name, item.get('startDate'), 'json_ld', place, event_url)
    if org == 'ARES':
        for m in re.finditer(r'(?m)^(\d{1,2}/\d{1,2}/\d{4})\s*\n(ARES[^\n]*)', page.text):
            add(m[2], m[1], 'ares_listing')
    if org == 'HEXAGONE':
        for m in re.finditer(r'(?m)^(HEXAGONE MMA[^\n]*)\s*\n(\d{1,2}/\d{1,2}/\d{2,4})\s*[–—-]\s*([^\n]+)', page.text):
            add(m[1], m[2], 'hexagone_listing', m[3])
    details = []
    for href, label in page.links:
        absolute = url.urljoin(address, href)
        p, root = url.urlsplit(absolute), url.urlsplit(address)
        if p.scheme != 'https' or p.hostname != root.hostname: continue
        if re.search(r'/(?:event|events|evenement|evenements)/[^/?#]+', p.path):
            canonical = url.urlunsplit((p.scheme, p.netloc, p.path.rstrip('/'), '', ''))
            if canonical not in details: details.append(canonical)
    return found, review, details

def compare(candidate, baseline):
    same_day = [e['id'] for e in baseline if e.get('org') == candidate['org'] and e.get('date') == candidate['date']]
    exact = [e for e in baseline if candidate.get('event_url') and candidate['event_url'].rstrip('/') in [str(e.get('url', '')).rstrip('/'), str(e.get('officialCardUrl', '')).rstrip('/')]]
    result = dict(candidate)
    result['possible_existing_ids'] = [e['id'] for e in exact] or same_day
    result['proposal'] = 'possible_update' if exact else 'possible_existing' if same_day else 'new_candidate'
    if exact:
        result['differences'] = {k: {'before': exact[0].get(k), 'observed': candidate[k]} for k in ('date', 'title', 'place') if candidate.get(k) and candidate[k] != exact[0].get(k)}
    return result

def collect(baseline, today):
    report = {'mode': 'dry_run', 'database_writes': False, 'as_of': today, 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'sources': [], 'candidates': [], 'review': [], 'not_implemented': ['Cartes de combats et palmarès', 'Adaptateurs Sherdog et Tapology', 'Publication et écriture Supabase']}
    seen = set()
    for org, kind, address in SOURCES:
        entry = {'org': org, 'url': address, 'status': 'pending', 'pages_read': 0, 'errors': [], 'coverage': 'partial'}
        report['sources'].append(entry)
        try:
            client = Client(address)
            html = client.get(address)
            entry['pages_read'] += 1
            found, review, links = parse_page(html, org, kind, address, today)
            report['review'].extend(review)
            entry['detail_links_found'] = len(links)
            for detail in links[:3]:
                try:
                    more, uncertain, _ = parse_page(client.get(detail), org, kind, detail, today)
                    entry['pages_read'] += 1
                    found.extend(more)
                    report['review'].extend(uncertain)
                except Exception as error: entry['errors'].append({'url': detail, 'reason': str(error)})
            entry['status'] = 'candidates_found' if found else 'needs_adapter_or_review'
            for item in found:
                identity = (item['org'], item['date'], item['title'].casefold(), item['source_url'])
                if identity not in seen:
                    seen.add(identity)
                    report['candidates'].append(compare(item, baseline))
        except Exception as error:
            entry['status'] = 'unavailable_or_disallowed'
            entry['errors'].append({'url': address, 'reason': str(error)})
    report['completed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='mma-data.json')
    parser.add_argument('--output', default='reports/discovery.json')
    parser.add_argument('--as-of', default=dt.datetime.now(ZoneInfo('Europe/Paris')).date().isoformat())
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.as_of).isoformat()
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))['events']
    report = collect(baseline, today)
    destination = Path(args.output)
    if destination.resolve() == Path(args.baseline).resolve(): raise ValueError('Le rapport ne doit pas remplacer les données initiales')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(destination), 'candidates': len(report['candidates']), 'sources': [{'url': s['url'], 'status': s['status']} for s in report['sources']]}, ensure_ascii=False))
    return 0 if any(s['status'] == 'candidates_found' for s in report['sources']) else 2

if __name__ == '__main__': raise SystemExit(main())
