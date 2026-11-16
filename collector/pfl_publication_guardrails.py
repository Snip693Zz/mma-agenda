"""Garde-fous de publication PFL : aucune écriture ni publication automatique.

Transforme un rapport de découverte PFL en propositions de création contrôlées.
Une proposition n'est éligible que si l'URL est unique, la fiche est à venir,
le titre et la date sont établis, et l'événement n'existe pas déjà.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def _canonical(value: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(value or '')
    if parsed.scheme != 'https' or not parsed.hostname:
        return ''
    host = parsed.hostname.removeprefix('www.')
    return urlunsplit(('https', host, parsed.path.rstrip('/'), '', ''))


def build_proposals(discovery_report: dict, existing_events: list[dict], today: str | None = None) -> dict:
    """Produit des propositions de création contrôlées, sans écriture."""
    today = today or dt.date.today().isoformat()
    existing_urls = {
        _canonical(event.get('url') or '')
        for event in existing_events
        if event.get('url')
    }
    existing_urls |= {
        _canonical(event.get('official_card_url') or '')
        for event in existing_events
        if event.get('official_card_url')
    }
    existing_urls.discard('')
    proposals = []
    for candidate in discovery_report.get('candidates', []):
        metadata = candidate.get('metadata') or {}
        url = _canonical(candidate.get('source_url') or '')
        title = str(metadata.get('title') or '').strip()
        date = str(metadata.get('date') or '').strip()
        try:
            upcoming = bool(date) and dt.date.fromisoformat(date) >= dt.date.fromisoformat(today)
        except ValueError:
            upcoming = False
        eligible = (
            bool(url)
            and url not in existing_urls
            and bool(title)
            and upcoming
            and metadata.get('status') == 'metadata_found'
        )
        proposal = {
            'source_url': url,
            'title': title,
            'date': date,
            'place': metadata.get('place') or '',
            'proposal': 'create_event' if eligible else 'review_required',
            'auto_publishable': False,
            'requires_manual_approval': True,
            'database_writes': False,
            'automatic_publication': False,
        }
        if eligible:
            proposed_id = 'pfl-auto-' + hashlib.sha256(url.encode()).hexdigest()[:12]
            proposal['proposed_event_id'] = proposed_id
            proposal['payload'] = {
                'event': {
                    'id': proposed_id,
                    'org': 'PFL',
                    'title': title,
                    'date': date,
                    'place': proposal['place'] or 'Lieu à confirmer',
                    'official': False,
                    'url': url,
                    'official_card_url': url,
                    'note': 'Événement PFL découvert depuis la fiche officielle. Cartes et combats à confirmer.',
                }
            }
        proposals.append(proposal)
    summary = {
        'candidates': len(proposals),
        'create_event': sum(item['proposal'] == 'create_event' for item in proposals),
        'review_required': sum(item['proposal'] == 'review_required' for item in proposals),
        'auto_publishable': 0,
    }
    return {
        'schema_version': 1,
        'mode': 'pfl_publication_guardrails',
        'automatic_publication': False,
        'database_writes': False,
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'proposals': proposals,
        'summary': summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Garde-fous de publication PFL en mode rapport')
    parser.add_argument('--discovery', required=True)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', default='reports/pfl-publication-guardrails.json')
    parser.add_argument('--as-of', default=dt.date.today().isoformat())
    args = parser.parse_args()
    discovery = json.loads(Path(args.discovery).read_text(encoding='utf-8'))
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
    report = build_proposals(discovery, baseline.get('events', []), args.as_of)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
