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

from update_reconciliation import compare_event, summarize

PFL_HOSTS = {'pflmma.com', 'www.pflmma.com'}
TAG_RE = re.compile(r'<[^>]+>')
NOISE = ('pfl record', 'career record', 'professional record', 'winner', 'method', 'round', 'time')


def clean_text(value: str) -> str:
    return re.sub(r'\s+', ' ', TAG_RE.sub(' ', value or '')).strip()


def extract_fights(html: str) -> list[dict]:
    """Extrait les paires affichées avec « vs » ; extraction prudente, à valider."""
    if not isinstance(html, str):
        return []
    text = clean_text(html)
    fights = []
    seen = set()
    for match in re.finditer(r'([^\n]{2,80}?)\s+(?:vs\.?|VS)\s+([^\n]{2,80})', text):
        a, b = clean_text(match.group(1)), clean_text(match.group(2))
        if not a or not b:
            continue
        lowered = (a + ' ' + b).lower()
        if any(word in lowered for word in NOISE):
            continue
        key = tuple(sorted((a.casefold(), b.casefold())))
        if key in seen:
            continue
        seen.add(key)
        fights.append({'fighter_a': a, 'fighter_b': b, 'card_position': 0, 'position': len(fights)})
    return fights


def fetch_page(url: str, timeout: int = 20) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in PFL_HOSTS or parsed.username or parsed.password:
        raise ValueError('URL PFL non autorisée')
    request = Request(url, headers={'User-Agent': 'mma-agenda-pfl-reconciliation/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError(f'Réponse PFL invalide : {response.status}')
            return response.read().decode('utf-8', errors='replace')
    except HTTPError as error:
        if error.code == 404:
            raise ValueError('Fiche PFL introuvable (404)') from error
        raise


def reconcile_event(event: dict, existing_fights: list[dict], html: str) -> dict:
    observed = extract_fights(html)
    source_kind = 'official' if event.get('official') else 'secondary'
    payload_event = dict(event)
    payload_event['source_kind'] = source_kind
    proposals = compare_event(payload_event, existing_fights, observed)
    return {
        'event_id': event.get('id'),
        'event': event.get('title'),
        'source_url': event.get('url'),
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
    payload = dict(report)
    payload['source_report'] = 'pfl_reconciliation_report'
    payload['source_sha256'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    result = client.rpc('record_update_reconciliation_v1', {'p_report': payload}).execute()
    return result.data[0] if result.data else {}


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
