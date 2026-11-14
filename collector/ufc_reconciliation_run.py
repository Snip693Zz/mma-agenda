"""Rapprochement UFC réel : lecture Supabase et rapport uniquement."""
import argparse
import json
import os
from pathlib import Path

try:
    from .daily_refresh_readonly import load_live
    from .ufc_cards_review import collect_reviewed
    from .discover import Client
    from .ufc_event_details import extract_details
    from .ufc_daily_reconciliation import reconcile
except ImportError:
    from daily_refresh_readonly import load_live
    from ufc_cards_review import collect_reviewed
    from discover import Client
    from ufc_event_details import extract_details
    from ufc_daily_reconciliation import reconcile

EXPECTED_URL = 'https://wxrxjwfktdviiasixupk.supabase.co'

def collect_details(cards, fetch_html, extract=extract_details):
    if not isinstance(cards, dict) or not isinstance(cards.get('events'), list):
        raise ValueError('Relevé UFC invalide')
    details = {}
    errors = []
    for event in cards['events']:
        if event.get('status') != 'parsed':
            continue
        address = event.get('source_url')
        if not isinstance(address, str) or not address:
            errors.append({'phase': 'ufc_details', 'reason': 'URL de fiche UFC manquante'})
            continue
        if address in details:
            errors.append({'phase': 'ufc_details', 'source': address, 'reason': 'Fiche UFC dupliquée'})
            continue
        try:
            details[address] = extract(fetch_html(address), address)
        except Exception as error:
            errors.append({'phase': 'ufc_details', 'source': address, 'exception_type': type(error).__name__, 'reason': 'Extraction UFC indisponible ou invalide'})
    return details, errors

def build_report(baseline, cards, html_by_url, extract=extract_details, reconciler=reconcile):
    getter = html_by_url.get if isinstance(html_by_url, dict) else html_by_url
    details, errors = collect_details(cards, getter, extract)
    report = reconciler(baseline, details)
    report['source'] = 'supabase_live_and_ufc_official_pages'
    report['database_read'] = True
    report['database_writes'] = False
    report['fallback_writes'] = False
    report['automatic_publication'] = False
    report['cards_generated_at'] = cards.get('generated_at')
    report['errors'] = list(report.get('errors') or []) + errors
    for entry in report.get('entries', []):
        entry['requires_review'] = True
        entry['ready_to_publish'] = False
        entry['auto_publishable'] = False
    return report

def run(client, fetch_html, extract=extract_details, reconciler=reconcile):
    report = {'mode': 'ufc_daily_reconciliation', 'database_read': False, 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'entries': [], 'errors': []}
    phase = 'supabase_read'
    try:
        baseline = load_live(client)
        report['database_read'] = True
        phase = 'ufc_collection'
        cards = collect_reviewed(baseline)
        report['cards_generated_at'] = cards.get('generated_at')
        report['errors'].extend(cards.get('errors') or [])
        phase = 'ufc_details'
        report = build_report(baseline, cards, fetch_html, extract, reconciler)
    except Exception as error:
        report.setdefault('errors', []).append({'phase': phase, 'exception_type': type(error).__name__, 'reason': 'Échec de rapprochement ; détails sensibles non enregistrés'})
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='reports/ufc-reconciliation.json')
    args = parser.parse_args()
    report = {'mode': 'ufc_daily_reconciliation', 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'entries': [], 'errors': []}
    try:
        from supabase import create_client
        from urllib.request import urlopen
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        if url != EXPECTED_URL or not key:
            raise ValueError('Configuration Supabase manquante ou inattendue')
        client = create_client(url, key)
        def fetch(address):
            with urlopen(address, timeout=30) as response:
                if response.status != 200:
                    raise ValueError('Réponse UFC invalide')
                return response.read().decode('utf-8')
        report = run(client, fetch)
    except Exception as error:
        report.setdefault('errors', []).append({'phase': 'configuration', 'exception_type': type(error).__name__})
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'mode': report['mode'], 'summary': report.get('summary', {}), 'errors': len(report.get('errors', [])), 'database_writes': False}))
    return 2 if report.get('errors') or any(entry.get('status') == 'blocked' for entry in report.get('entries', [])) else 0

if __name__ == '__main__':
    raise SystemExit(main())
