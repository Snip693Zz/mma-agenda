"""Découverte PFL en mode rapport : aucune écriture ni publication automatique.

Le module lit le calendrier officiel PFL, identifie les fiches d'événements,
extrait les métadonnées JSON-LD lorsqu'elles sont disponibles et les rapproche
des événements déjà connus par URL canonique.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

PFL_HOSTS = {'pflmma.com', 'www.pflmma.com'}
EVENT_PATH_RE = re.compile(r'/event/[A-Za-z0-9-]+/?$')


def canonical_url(value: str) -> str:
    parsed = urlsplit(value or '')
    if parsed.scheme != 'https' or not parsed.hostname:
        return ''
    host = parsed.hostname.removeprefix('www.')
    return urlunsplit(('https', host, parsed.path.rstrip('/'), '', ''))


def validate_official_url(value: str) -> str:
    parsed = urlsplit(value or '')
    if (parsed.scheme != 'https' or parsed.hostname not in PFL_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment
            or not (parsed.path == '/events' or EVENT_PATH_RE.fullmatch(parsed.path.rstrip('/') + '/'))):
        raise ValueError('URL de calendrier ou fiche PFL officielle attendue')
    return value


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != 'a':
            return
        attributes = dict(attrs)
        candidate = urljoin(self.base_url, attributes.get('href') or '')
        try:
            validate_official_url(candidate)
        except ValueError:
            return
        if EVENT_PATH_RE.fullmatch(urlsplit(candidate).path.rstrip('/') + '/'):
            self.links.add(canonical_url(candidate))


def extract_event_links(listing_html: str, listing_url: str) -> list[str]:
    """Extrait les fiches PFL officielles du calendrier, dédupliquées."""
    validate_official_url(listing_url)
    parser = _LinkParser(listing_url)
    parser.feed(listing_html or '')
    parser.close()
    return sorted(parser.links)


def _iter_jsonld(value):
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld(item)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_jsonld(child)


def extract_event_metadata(event_html: str, event_url: str) -> dict:
    """Extrait un événement JSON-LD unique correspondant à la fiche demandée."""
    validate_official_url(event_url)
    expected = canonical_url(event_url)
    matches: list[dict] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        event_html or '',
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue
        for item in _iter_jsonld(payload):
            types = item.get('@type', [])
            types = types if isinstance(types, list) else [types]
            if 'Event' not in types:
                continue
            item_url = canonical_url(str(item.get('url') or ''))
            if item_url and item_url == expected:
                matches.append(item)
    if len(matches) != 1:
        return {'status': 'needs_review', 'reason': 'jsonld_event_not_unique'}
    item = matches[0]
    title = str(item.get('name') or '').strip()
    start = str(item.get('startDate') or '').strip()
    date = start[:10]
    try:
        parsed_date = dt.date.fromisoformat(date)
    except ValueError:
        return {'status': 'needs_review', 'reason': 'jsonld_start_date_invalid'}
    return {
        'status': 'metadata_found',
        'title': title,
        'date': parsed_date.isoformat(),
        'start_at': start,
        'place': str(item.get('location', {}).get('name') or '').strip() if isinstance(item.get('location'), dict) else '',
        'url': expected,
    }


def classify_candidate(metadata: dict, existing_urls: set[str], today: str) -> dict:
    url = metadata.get('url') or ''
    if url in existing_urls:
        proposal = 'existing_event'
    elif metadata.get('status') == 'metadata_found':
        proposal = 'new_candidate'
    else:
        proposal = 'review_required'
    upcoming = bool(metadata.get('date') and metadata['date'] >= today)
    return {
        'source_url': url,
        'proposal': proposal,
        'upcoming': upcoming,
        'automatic_publication': False,
        'database_writes': False,
    }


def build_discovery_report(
    listing_html: str,
    listing_url: str,
    event_pages: dict[str, str],
    existing_events: list[dict],
    today: str,
) -> dict:
    """Produit un rapport de découverte sans écrire dans la base."""
    validate_official_url(listing_url)
    links = extract_event_links(listing_html, listing_url)
    existing_urls = {
        canonical_url(event.get('url') or '')
        for event in existing_events
        if event.get('url')
    }
    existing_urls |= {
        canonical_url(event.get('official_card_url') or '')
        for event in existing_events
        if event.get('official_card_url')
    }
    existing_urls.discard('')
    candidates = []
    for url in links:
        metadata = extract_event_metadata(event_pages.get(url, ''), url)
        classification = classify_candidate(metadata, existing_urls, today)
        candidates.append({
            'source_url': url,
            'metadata': metadata,
            **classification,
        })
    summary = {
        'event_links': len(links),
        'metadata_found': sum(item['metadata']['status'] == 'metadata_found' for item in candidates),
        'new_candidates': sum(item['proposal'] == 'new_candidate' for item in candidates),
        'existing_events': sum(item['proposal'] == 'existing_event' for item in candidates),
        'review_required': sum(item['proposal'] == 'review_required' for item in candidates),
        'upcoming': sum(item['upcoming'] for item in candidates),
    }
    return {
        'schema_version': 1,
        'mode': 'pfl_discovery_report',
        'automatic_publication': False,
        'database_writes': False,
        'listing_url': canonical_url(listing_url),
        'as_of': today,
        'candidates': candidates,
        'summary': summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Découverte PFL en mode rapport')
    parser.add_argument('--listing-html', required=True)
    parser.add_argument('--listing-url', default='https://pflmma.com/events')
    parser.add_argument('--events-json', required=True, help='JSON {url: html}')
    parser.add_argument('--baseline', required=True, help='JSON {events: [...]}')
    parser.add_argument('--output', default='reports/pfl-discovery.json')
    parser.add_argument('--as-of', default=dt.date.today().isoformat())
    args = parser.parse_args()
    listing_html = Path(args.listing_html).read_text(encoding='utf-8')
    event_pages = json.loads(Path(args.events_json).read_text(encoding='utf-8'))
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
    report = build_discovery_report(
        listing_html,
        args.listing_url,
        event_pages,
        baseline.get('events', []),
        args.as_of,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
