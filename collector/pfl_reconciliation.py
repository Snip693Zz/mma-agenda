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


def extract_event_date(html: str) -> str | None:
    """Unique French date in primary content; ambiguous or invalid means unknown."""
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
    return next(iter(dates)) if len(dates) == 1 else None


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
            raise ValueError('Réponse PFL non valide')
        return response.read().decode('utf-8')


def reconcile_event(event: dict, existing_fights: list[dict], html: str) -> dict:
    source_url = str(event.get('url') or '')
    observed = extract_structured_fights(html, source_url)
    source_kind = 'official' if event.get('official') else 'secondary'
    observed_date = extract_event_date(html) or ''
    validation = assess_source(
        str(event.get('date') or observed_date),
        observed_date,
        identity_verified=extract_event_identity(html, event),
        structured_card=bool(observed),
        fight_count=len(observed),
    )
    payload_event = dict(event)
    payload_event['source_kind'] = source_kind
    proposals = []
    if validation['can_reconcile'] and observed:
        proposals = compare_event(payload_event, existing_fights, observed)
    return {
        'event_id': event.get('id'),
        'event': event.get('title'),
        'source_url': event.get('url'),
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


def build_report(events: list[dict], fights_by_event: dict[str, list[dict]], fetcher=fetch_page) -> dict:
    reports, errors = [], []
    for event in events:
        try:
            html = fetcher(event.get('url') or '')
            reports.append(reconcile_event(event, fights_by_event.get(event.get('id'), []), html))
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
    result = client.rpc('record_update_reconciliation_v1', {'p_report': payload}).execute()
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
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    client = supabase_client()
    events = client.table('events').select('*').eq('org', 'PFL').execute().data or []
    if args.limit > 0:
        events = events[:args.limit]
    fights_by_event = {}
    if events:
        fights = client.table('fights').select('event_id,card_position,position,fighter_a,fighter_b').in_('event_id', [event['id'] for event in events]).execute().data or []
        for fight in fights:
            fights_by_event.setdefault(fight['event_id'], []).append(fight)

    report = build_report(events, fights_by_event)
    if args.apply:
        report['saved'] = save_report(client, report)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'events': len(events), 'proposals': report['summary']['total'], 'errors': len(report['errors']), 'saved': report.get('saved')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
