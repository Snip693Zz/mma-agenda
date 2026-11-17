"""Flux quotidien PFL : découverte en mode rapport, sans écriture ni publication."""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

try:
    from .pfl_discovery import build_discovery_report, classify_candidate, validate_official_url
except ImportError:
    from pfl_discovery import build_discovery_report, classify_candidate, validate_official_url

LISTING_URL = 'https://pflmma.com/events'
MAX_BYTES = 5_000_000


def fetch_page(url: str, opener=None) -> str:
    """Récupère une page PFL officielle en HTTPS, sans redirection."""
    validate_official_url(url)
    request = Request(
        url,
        headers={
            'User-Agent': 'mma-agenda/1.0 (+https://github.com/Snip693Zz/mma-agenda)',
            'Accept': 'text/html',
            'Accept-Encoding': 'identity',
        },
    )
    with (opener or build_opener()).open(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Réponse PFL non valide')
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Contenu non HTML')
        raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('Taille de source invalide')
        charset = response.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset)


def supabase_client():
    from supabase import create_client

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis')
    return create_client(url, key)


def load_pfl_events(client) -> list[dict]:
    rows = client.table('events').select('id,url,official_card_url,title,event_date').eq('org', 'PFL').execute().data or []
    if not isinstance(rows, list):
        raise ValueError('Réponse Supabase invalide')
    return rows


def run_daily_discovery(
    client,
    fetcher=fetch_page,
    today: str | None = None,
    limit: int = 20,
    pause=time.sleep,
) -> dict:
    """Produit un rapport quotidien de découverte PFL, sans écriture."""
    if not 1 <= limit <= 50:
        raise ValueError('Limite de fiches invalide')
    today = today or dt.date.today().isoformat()
    existing_events = load_pfl_events(client)
    listing_html = fetcher(LISTING_URL)
    from pfl_discovery import extract_event_links

    links = extract_event_links(listing_html, LISTING_URL)[:limit]
    event_pages: dict[str, str] = {}
    errors: list[dict] = []
    for index, url in enumerate(links):
        if index:
            pause(1)
        try:
            event_pages[url] = fetcher(url)
        except (HTTPError, URLError, ValueError, http.client.HTTPException, TimeoutError, OSError) as error:
            errors.append({'source_url': url, 'reason': str(error)[:500]})
    report = build_discovery_report(listing_html, LISTING_URL, event_pages, existing_events, today)
    report['errors'] = errors
    report['summary']['fetch_errors'] = len(errors)
    report['summary']['pages_fetched'] = len(event_pages)
    return report


def run_browser_discovery(client, browser_report_path: str, today: str, limit: int) -> dict:
    """Classifie un rapport de découverte navigateur PFL, sans écriture."""
    if not 1 <= limit <= 50:
        raise ValueError('Limite de fiches invalide')
    browser_report = json.loads(Path(browser_report_path).read_text(encoding='utf-8'))
    if browser_report.get('mode') != 'pfl_browser_discovery':
        raise ValueError('Rapport de découverte navigateur invalide')
    existing_events = load_pfl_events(client)
    existing_urls = set()
    for event in existing_events:
        for key in ('url', 'official_card_url'):
            canonical = ''
            try:
                canonical = validate_official_url(event.get(key) or '')
            except ValueError:
                canonical = ''
            if canonical:
                existing_urls.add(canonical.rstrip('/'))
    candidates = []
    errors = []
    for item in browser_report.get('candidates', [])[:limit]:
        url = item.get('source_url') or ''
        try:
            validate_official_url(url)
        except ValueError as error:
            errors.append({'source_url': url, 'reason': str(error)[:500]})
            continue
        title = (item.get('title') or '').strip()
        date = (item.get('date') or '').strip()
        valid_date = False
        if date:
            try:
                dt.date.fromisoformat(date)
                valid_date = True
            except ValueError:
                valid_date = False
        metadata = {
            'status': 'metadata_found' if title and valid_date else 'needs_review',
            'title': title,
            'date': date if valid_date else '',
            'start_at': item.get('start_at') or '',
            'place': '',
            'url': url.rstrip('/'),
        }
        classification = classify_candidate(metadata, existing_urls, today)
        candidates.append({
            'source_url': url.rstrip('/'),
            'metadata': metadata,
            'observed_pairs': item.get('pairs') or [],
            'row_count': item.get('row_count') or 0,
            'extraction_status': item.get('extraction_status') or 'not_available',
            'card_html': item.get('card_html') or '',
            **classification,
        })
        if item.get('error'):
            errors.append({'source_url': url, 'reason': item['error'][:500]})
    summary = {
        'event_links': browser_report.get('summary', {}).get('event_links', 0),
        'metadata_found': sum(item['metadata']['status'] == 'metadata_found' for item in candidates),
        'new_candidates': sum(item['proposal'] == 'new_candidate' for item in candidates),
        'existing_events': sum(item['proposal'] == 'existing_event' for item in candidates),
        'review_required': sum(item['proposal'] == 'review_required' for item in candidates),
        'upcoming': sum(item['upcoming'] for item in candidates),
        'fetch_errors': len(errors),
        'pages_fetched': len(candidates),
    }
    return {
        'schema_version': 1,
        'mode': 'pfl_browser_discovery_report',
        'automatic_publication': False,
        'database_writes': False,
        'listing_url': browser_report.get('listing_url', LISTING_URL),
        'as_of': today,
        'candidates': candidates,
        'errors': errors,
        'summary': summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Découverte quotidienne PFL en mode rapport')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--output', default='reports/pfl-daily-discovery.json')
    parser.add_argument('--as-of', default=dt.date.today().isoformat())
    parser.add_argument('--browser-report', default='')
    args = parser.parse_args()
    client = supabase_client()
    if args.browser_report:
        report = run_browser_discovery(client, args.browser_report, args.as_of, args.limit)
    else:
        report = run_daily_discovery(client, today=args.as_of, limit=args.limit)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))
    return 0 if not report['errors'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
