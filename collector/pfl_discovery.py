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
MONTHS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}


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
        self.links: list[str] = []
        self.seen: set[str] = set()

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
            url = canonical_url(candidate)
            if url not in self.seen:
                self.seen.add(url)
                self.links.append(url)


def extract_event_links(listing_html: str, listing_url: str) -> list[str]:
    """Extrait les fiches PFL officielles du calendrier, dédupliquées."""
    validate_official_url(listing_url)
    parser = _LinkParser(listing_url)
    parser.feed(listing_html or '')
    parser.close()
    return parser.links


def _iter_jsonld(value):
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld(item)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_jsonld(child)


def _extract_html_metadata(event_html: str, expected: str) -> dict:
    """Repli HTML strict : titre et date valide requis, sinon revue."""
    html = event_html or ''
    title = ''
    og = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og:
        title = og.group(1).strip()
    else:
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
        if h1:
            title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
    start = ''
    date = ''
    time_match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if time_match:
        raw = time_match.group(1).strip()
        try:
            parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
            date = parsed.date().isoformat()
            start = raw
        except ValueError:
            date = ''
    if not date:
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        day_match = re.search(r'\b(?:MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\b', text, re.IGNORECASE)
        if day_match:
            month = MONTHS.get(day_match.group(1).upper())
            day = int(day_match.group(2))
            year_match = re.search(r'\b(20\d{2})\b', text[day_match.end():])
            if month and year_match:
                try:
                    date = dt.date(int(year_match.group(1)), month, day).isoformat()
                except ValueError:
                    date = ''
    if title and date:
        return {
            'status': 'metadata_found',
            'title': title,
            'date': date,
            'start_at': start,
            'place': '',
            'url': expected,
        }
    return {'status': 'needs_review', 'reason': 'metadata_not_found'}


def extract_event_metadata(event_html: str, event_url: str) -> dict:
    """Extrait un événement JSON-LD unique correspondant à la fiche demandée."""
    validate_official_url(event_url)
    expected = canonical_url(event_url)
    expected_path = urlsplit(expected).path.rstrip('/')
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
            item_path = urlsplit(item_url).path.rstrip('/')
            if item_path and item_path == expected_path:
                matches.append(item)
    if len(matches) == 1:
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
    try:
        from .pfl_scoped_metadata import extract_scoped_metadata
    except ImportError:
        from pfl_scoped_metadata import extract_scoped_metadata
    return extract_scoped_metadata(event_html, expected)


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
    """Classifie uniquement les pages fournies, sans écriture en base."""
    validate_official_url(listing_url)
    links = extract_event_links(listing_html, listing_url)
    pages = {}
    for source_url, html in event_pages.items():
        validate_official_url(source_url)
        url = canonical_url(source_url)
        if url not in links:
            raise ValueError(f'Fiche absente du listing PFL : {url}')
        if not isinstance(html, str):
            raise ValueError(f'Contenu HTML invalide : {url}')
        pages[url] = html
    existing_urls = {
        canonical_url(event.get(key) or '')
        for event in existing_events
        for key in ('url', 'official_card_url')
    }
    existing_urls.discard('')
    candidates = []
    for url in links:
        if url not in pages:
            continue
        html = pages[url]
        metadata = dict(extract_event_metadata(html, url))
        metadata['url'] = url
        classification = classify_candidate(metadata, existing_urls, today)
        candidates.append({
            **classification,
            'source_url': url,
            'metadata': metadata,
            'extraction_status': metadata['status'],
            'diagnostic': {
                'html_characters': len(html),
                'has_jsonld': bool(re.search(r'application/ld\+json', html, re.IGNORECASE)),
                'has_h1': bool(re.search(r'<h1\b', html, re.IGNORECASE)),
                'has_time_datetime': bool(re.search(r'<time\b[^>]*\bdatetime\s*=', html, re.IGNORECASE)),
                'reason': metadata.get('reason', ''),
            },
        })
    metadata_found = sum(item['metadata']['status'] == 'metadata_found' for item in candidates)
    summary = {
        'event_links': len(links),
        'pages_fetched': len(pages),
        'not_inspected': len(links) - len(pages),
        'metadata_found': metadata_found,
        'metadata_missing': len(candidates) - metadata_found,
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
        'diagnostics': {
            'no_event_links': not links,
            'no_metadata_on_fetched_pages': bool(pages) and metadata_found == 0,
        },
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
