"""Collecteur PFL de rapprochement des cartes.

Lit les fiches officielles PFL, extrait prudemment les combats affichés,
les compare à Supabase et produit un rapport. Aucune publication automatique
n'est déclenchée par ce module : les propositions restent à valider.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    from .source_validation import assess_source
except ImportError:
    from source_validation import assess_source

try:
    from .pfl_card_structure import extract_structured_fights
except ImportError:
    from pfl_card_structure import extract_structured_fights

try:
    from .pfl_primary_identity import primary_identity_matches
    from .pfl_section_candidates import TextTree
except ImportError:
    from pfl_primary_identity import primary_identity_matches
    from pfl_section_candidates import TextTree

try:
    from .update_reconciliation import compare_event, summarize
except ImportError:
    from update_reconciliation import compare_event, summarize
PFL_HOSTS = {'pflmma.com', 'www.pflmma.com'}
TAG_RE = re.compile(r'<[^>]+>')
NOISE = ('pfl record', 'career record', 'professional record', 'winner', 'method', 'round', 'time', 'faceoff', 'face-off')
DATE_RE = re.compile(r'\b(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})\b', re.IGNORECASE)
MONTHS = {'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12}
EN_DATE_RE = re.compile(r'\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\b', re.IGNORECASE)
EN_MONTHS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}


def clean_text(value: str) -> str:
    return re.sub(r'\s+', ' ', TAG_RE.sub(' ', value or '')).strip()


def extract_fights(html: str) -> list[dict]:
    """Extraction textuelle conservée pour les diagnostics ; non utilisée pour valider une carte."""
    if not isinstance(html, str):
        return []
    fights = []
    seen = set()
    for segment in re.split(r'<[^>]+>', html):
        text = clean_text(segment)
        if not text:
            continue
        match = re.search(r'^(.{2,80}?)\s+(?:vs\.?|VS)\s+(.{2,80})$', text, re.IGNORECASE)
        if not match:
            continue
        fighter_a = match.group(1).strip()
        fighter_b = match.group(2).strip()
        if not fighter_a or not fighter_b:
            continue
        lowered = (fighter_a + ' ' + fighter_b).lower()
        if any(word in lowered for word in NOISE):
            continue
        key = tuple(sorted((fighter_a.casefold(), fighter_b.casefold())))
        if key in seen:
            continue
        seen.add(key)
        fights.append({'fighter_a': fighter_a, 'fighter_b': fighter_b, 'card_position': 0, 'position': len(fights)})
    return fights


def extract_event_date(html: str, source_url: str = '') -> str | None:
    """Date officielle visible dans le contenu principal ; ambiguïté signifie inconnu."""
    if not isinstance(html, str):
        return None
    tree = TextTree(html)
    if tree.malformed or len(tree.stack) != 1:
        return None
    excluded = {'header', 'nav', 'footer', 'aside', 'script', 'style', 'template'}
    def visible(node):
        if node.tag in excluded:
            return
        yield node
        for child in node.children:
            yield from visible(child)
    mains = [n for n in visible(tree.root) if n.tag == 'main']
    if len(mains) > 1:
        return None
    scope = mains[0] if mains else tree.root
    nodes = list(visible(scope))
    if sum(n.tag == 'h1' for n in nodes) != 1:
        return None
    dates = set()
    for node in nodes:
        for day, month, year in DATE_RE.findall(getattr(node, 'text', '')):
            try:
                dates.add(dt.date(int(year), MONTHS[month.lower()], int(day)).isoformat())
            except (ValueError, KeyError):
                return None
    english_dates = set()
    for node in nodes:
        for _, month_text, day_text in EN_DATE_RE.findall(getattr(node, 'text', '')):
            month = EN_MONTHS.get(month_text.upper())
            if not month:
                continue
            english_dates.add((month, int(day_text)))
    if len(dates) == 1:
        return next(iter(dates))
    if len(dates) > 1:
        return None
    if len(english_dates) != 1:
        return None
    month, day = next(iter(english_dates))
    url_year_match = re.search(r'(?:^|[-/])(20\d{2})(?:[-/]|$)', source_url or '')
    if url_year_match:
        try:
            return dt.date(int(url_year_match.group(1)), month, day).isoformat()
        except ValueError:
            return None
    now = dt.date.today()
    candidate = dt.date(now.year, month, day)
    if candidate >= now:
        return candidate.isoformat()
    return None


def extract_event_identity(html: str, event: dict) -> bool:
    return primary_identity_matches(html, event)


def fetch_page(url: str) -> str:
    """Récupère uniquement une fiche PFL officielle en HTTPS."""
    source = urlsplit(url)
    if (source.scheme != 'https' or source.netloc not in PFL_HOSTS
            or source.query or source.fragment or not re.fullmatch(r'/event/[a-zA-Z0-9-]+/?', source.path)):
        raise ValueError('Fiche PFL officielle requise')
    request = Request(url, headers={'User-Agent': 'mma-agenda/1.0 (+https://github.com/Snip693Zz/mma-agenda)'})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Fiche PFL non valide')
        return response.read().decode('utf-8')


def normalized_slug(url: str) -> str:
    try:
        slug = urlsplit(url or '').path.rstrip('/').split('/')[-1].lower()
    except ValueError:
        return ''
    return re.sub(r'-20\d{2}$', '', slug)


def load_discovery_candidates(path: str) -> dict[str, dict]:
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if report.get('mode') != 'pfl_browser_discovery_report':
        raise ValueError('Rapport de découverte PFL invalide')
    candidates = {}
    for item in report.get('candidates', []):
        metadata = item.get('metadata') or {}
        date = str(metadata.get('date') or '').strip()
        card_html = item.get('card_html') or ''
        if not date or not card_html:
            continue
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            continue
        slug = normalized_slug(item.get('source_url') or '')
        if slug and slug not in candidates:
            candidates[slug] = {
                'source_url': item.get('source_url') or '',
                'date': date,
                'card_html': card_html,
                'page_html': item.get('page_html') or '',
            }
    return candidates


def active_card_fights(event_id: str, fights: list[dict], cards: list[dict]) -> list[dict]:
    """Never compare historical or orphaned fights as current fights."""
    active_positions = {c['position'] for c in cards
                        if c.get('event_id') == event_id and c.get('is_active') is True}
    if not active_positions:
        raise ValueError('Aucune carte active connue : rapprochement refusé')
    return [dict(f) for f in fights if f.get('event_id') == event_id
            and f.get('card_position') in active_positions]


def guard_unknown_allocation(proposals: list[dict]) -> None:
    """The structured extractor supplies order, not a validated card allocation."""
    for proposal in proposals:
        proposal['auto_publishable'] = False
        if proposal['kind'] != 'add_fight':
            continue
        payload = proposal['payload']
        payload['card_position'] = None
        payload['allocation'] = 'unassigned'
        proposal['evidence']['allocation'] = 'unassigned'
        proposal['evidence']['source_position'] = payload.get('position')
        proposal['evidence']['publication_requires_card_assignment'] = True
        proposal['reason'] += ' ; répartition de carte non validée, affectation requise avant publication'


def reconcile_event(event: dict, existing_fights: list[dict], html: str, discovery: dict | None = None) -> dict:
    source_url = str(event.get('url') or '')
    page_html = ''
    if discovery:
        source_url = str(discovery.get('source_url') or source_url)
        html = str(discovery.get('card_html') or html)
        page_html = str(discovery.get('page_html') or '')
    observed = extract_structured_fights(html, source_url, allow_fragment=True)
    for fight in observed:
        fight['card_position'] = None
        fight['allocation'] = 'unassigned'
    source_kind = 'official' if event.get('official') else 'secondary'
    if discovery:
        observed_date = str(discovery.get('date') or '')
    else:
        observed_date = extract_event_date(html, source_url) or ''
    validation = assess_source(
        str(event.get('date') or observed_date),
        observed_date,
        identity_verified=extract_event_identity(page_html or html, event),
        structured_card=bool(observed),
        fight_count=len(observed),
    )
    payload_event = dict(event)
    payload_event['source_kind'] = source_kind
    payload_event['source_url'] = source_url
    proposals = []
    if validation['can_reconcile'] and observed:
        proposals = compare_event(payload_event, existing_fights, observed)
        guard_unknown_allocation(proposals)
    return {
        'event_id': event.get('id'),
        'event': event.get('title'),
        'source_url': source_url,
        'source_validation': validation,
        'observed_fights': observed,
        'proposals': proposals,
        'summary': summarize(proposals),
    }


def supabase_client():
    from supabase import create_client

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis')
    return create_client(url, key)


def build_report(events: list[dict], fights_by_event: dict[str, list[dict]], fetcher=fetch_page, discovery_candidates: dict[str, dict] | None = None, cards: list[dict] | None = None) -> dict:
    reports, errors = [], []
    discovery_candidates = discovery_candidates or {}
    for event in events:
        try:
            if cards is None:
                raise ValueError('Métadonnées de cartes requises pour exclure les cartes inactives')
            existing = active_card_fights(event['id'], fights_by_event.get(event['id'], []), cards)
            discovery = discovery_candidates.get(normalized_slug(event.get('url') or ''))
            if discovery:
                reports.append(reconcile_event(event, existing, '', discovery))
            else:
                html = fetcher(event.get('url') or '')
                reports.append(reconcile_event(event, existing, html))
        except (HTTPError, URLError, ValueError) as error:
            errors.append({'event_id': event.get('id'), 'url': event.get('url'), 'reason': str(error)})
    proposals = [proposal for report in reports for proposal in report['proposals']]
    return {
        'mode': 'pfl_reconciliation_report',
        'automatic_publication': False,
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'events_observed': len(reports),
        'fights_observed': sum(len(report['observed_fights']) for report in reports),
        'errors': errors,
        'reports': reports,
        'summary': summarize(proposals),
    }


def save_report(client, report: dict) -> dict:
    payload = {
        'mode': report.get('mode', 'pfl_reconciliation_report'),
        'source_report': 'pfl_reconciliation_report',
        'status': 'success' if not report.get('errors') else 'partial',
        'events_observed': report.get('events_observed', 0),
        'fights_observed': report.get('fights_observed', 0),
        'errors': len(report.get('errors', [])),
        'extra': {'report': report},
    }
    payload['source_sha256'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    result = client.rpc('record_pfl_reconciliation_v2', {'p_report': payload}).execute()
    data = result.data
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description='Rapprochement PFL en mode rapport')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--output', default='reports/pfl-reconciliation.json')
    parser.add_argument('--discovery', default='')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    client = supabase_client()
    events = client.table('events').select('*').eq('org', 'PFL').execute().data or []
    if args.limit > 0:
        events = events[:args.limit]
    fights_by_event = {}
    cards = []
    if events:
        event_ids = [event['id'] for event in events]
        cards = client.table('event_cards').select('event_id,position,is_active').in_('event_id', event_ids).execute().data or []
        fights = client.table('fights').select('event_id,card_position,position,fighter_a,fighter_b').in_('event_id', event_ids).execute().data or []
        for fight in fights:
            fights_by_event.setdefault(fight['event_id'], []).append(fight)

    discovery_candidates = load_discovery_candidates(args.discovery) if args.discovery else {}
    report = build_report(events, fights_by_event, discovery_candidates=discovery_candidates, cards=cards)
    if args.apply:
        report['saved'] = save_report(client, report)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'events': len(events), 'proposals': report['summary']['total'], 'errors': len(report['errors']), 'saved': report.get('saved')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
