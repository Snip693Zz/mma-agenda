"""Flux quotidien PFL : découverte en mode rapport, sans écriture ni publication."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

try:
    from .pfl_discovery import build_discovery_report, validate_official_url
except ImportError:
    from pfl_discovery import build_discovery_report, validate_official_url

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
        except (HTTPError, URLError, ValueError) as error:
            errors.append({'source_url': url, 'reason': str(error)[:500]})
    report = build_discovery_report(listing_html, LISTING_URL, event_pages, existing_events, today)
    report['errors'] = errors
    report['summary']['fetch_errors'] = len(errors)
    report['summary']['pages_fetched'] = len(event_pages)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Découverte quotidienne PFL en mode rapport')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--output', default='reports/pfl-daily-discovery.json')
    parser.add_argument('--as-of', default=dt.date.today().isoformat())
    args = parser.parse_args()
    client = supabase_client()
    report = run_daily_discovery(client, today=args.as_of, limit=args.limit)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))
    return 0 if not report['errors'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
