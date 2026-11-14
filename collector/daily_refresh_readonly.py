"""Rafraîchissement de validation : lectures Supabase uniquement, aucun publieur."""
import collections
import copy
import datetime as dt
import json
import os
from pathlib import Path

ORDER = {'events': ('id',), 'event_cards': ('event_id', 'position'), 'fights': ('event_id', 'card_position', 'position')}

def read_rows(client, table, page_size=500):
    rows = []
    offset = 0
    while True:
        query = client.table(table).select('*')
        for field in ORDER[table]:
            query = query.order(field)
        batch = query.range(offset, offset + page_size - 1).execute().data
        if not isinstance(batch, list):
            raise ValueError('Réponse de lecture invalide')
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size

def load_live(client, page_size=500):
    rows = {name: read_rows(client, name, page_size) for name in ORDER}
    events = {}
    cards = {}
    positions = set()
    for row in rows['events']:
        if row['id'] in events:
            raise ValueError('Événement dupliqué')
        events[row['id']] = {**copy.deepcopy(row), 'date': row['event_date'], 'officialCardUrl': row.get('official_card_url'), 'cards': []}
    for row in rows['event_cards']:
        key = (row['event_id'], row['position'])
        if row['event_id'] not in events or key in cards:
            raise ValueError('Carte orpheline ou dupliquée')
        card = {**copy.deepcopy(row.get('extra') or {}), 'position': row['position'], 'name': row['name'], 'start': row['start_at'], 'level': row['level'], 'source': row['source'], 'fights': []}
        cards[key] = card
    for row in sorted(rows['fights'], key=lambda r: (r['event_id'], r['card_position'], r['position'])):
        key = (row['event_id'], row['card_position'])
        position = (*key, row['position'])
        pair = [row['fighter_a'], row['fighter_b']]
        if key not in cards or position in positions or any(not isinstance(n, str) or not n.strip() for n in pair) or pair[0].strip() == pair[1].strip():
            raise ValueError('Combat orphelin, dupliqué ou invalide')
        positions.add(position)
        cards[key]['fights'].append(pair)
    for (event_id, position), card in sorted(cards.items()):
        events[event_id]['cards'].append(card)
    if not events:
        raise ValueError('Lecture des événements vide')
    return {'events': list(events.values()), 'fighterRecords': {}}

def title_diagnostic(entry, baseline, catalog):
    try:
        from .ufc_proposals import canonical
    except ImportError:
        from ufc_proposals import canonical
    previous = next((e for e in baseline.get('events', []) if e.get('id') == entry.get('existing_id')), None)
    address = canonical(entry.get('source_url'))
    titles = []
    for group in catalog.get('events', []):
        for item in group.get('observations', [group]):
            if address and canonical(item.get('source_url')) == address and item.get('source_kind') == 'official' and item.get('method') == 'ufc_hero_timestamp':
                title = item.get('title')
                if title not in titles:
                    titles.append(title)
    return {'existing_title': previous.get('title') if previous else None, 'observed_title': titles[0] if len(titles) == 1 else None, 'observed_titles': titles}

def run(client, collect, compare):
    report = {'mode': 'read_only', 'database_read': False, 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'entries': [], 'published': [], 'errors': []}
    phase = 'supabase_read'
    try:
        baseline = load_live(client)
        report['database_read'] = True
        report['baseline_counts'] = {'events': len(baseline['events']), 'cards': sum(len(e['cards']) for e in baseline['events']), 'fights': sum(len(c['fights']) for e in baseline['events'] for c in e['cards'])}
        phase = 'collection'
        observed, catalog = collect(baseline)
        phase = 'comparison'
        proposal = compare(observed, baseline, catalog)
        report.update({key: copy.deepcopy(value) for key, value in proposal.items() if key in ('entries', 'errors', 'summary', 'baseline_sha256', 'cards_generated_at')})
        if not report['entries']:
            report['errors'].append({'phase': phase, 'reason': 'Aucune fiche comparée'})
        for entry in report['entries']:
            entry['requires_review'] = True
            entry['ready_to_publish'] = False
            entry['auto_publishable'] = False
            if entry.get('type') in ('blocked', 'review_discrepancy'):
                entry.update(title_diagnostic(entry, baseline, catalog))
    except Exception as error:
        report['errors'].append({'phase': phase, 'exception_type': type(error).__name__, 'reason': 'Échec de validation ; détails sensibles non enregistrés'})
    return report

def diagnostic_lines(report):
    lines = []
    for entry in report.get('entries', []):
        if entry.get('type') not in ('blocked', 'review_discrepancy'):
            continue
        lines.append({'status': entry.get('type'), 'source_url': entry.get('source_url'), 'existing_id': entry.get('existing_id'), 'reason': entry.get('reason'), 'existing_title': entry.get('existing_title'), 'observed_title': entry.get('observed_title'), 'observed_titles': entry.get('observed_titles', []), 'new_pairs': entry.get('new_pairs', []), 'existing_not_observed': entry.get('existing_not_observed', [])})
    for error in report.get('errors', []):
        lines.append({'status': 'error', 'error': error})
    return lines

def main():
    report = {'mode': 'read_only', 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False, 'published': [], 'errors': []}
    try:
        from supabase import create_client
        from ufc_proposals import live, build
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        if url != 'https://wxrxjwfktdviiasixupk.supabase.co' or not key:
            raise ValueError('Configuration Supabase manquante ou inattendue')
        report = run(create_client(url, key), live, build)
    except Exception as error:
        report['errors'].append({'phase': 'configuration', 'exception_type': type(error).__name__})
    target = Path('reports/daily-refresh.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'mode': report['mode'], 'summary': report.get('summary', {}), 'errors': len(report['errors']), 'database_writes': False}))
    for line in diagnostic_lines(report):
        print(json.dumps(line, ensure_ascii=False))
    return 2 if report['errors'] or any(e.get('type') in ('blocked', 'review_discrepancy') for e in report.get('entries', [])) else 0

if __name__ == '__main__':
    raise SystemExit(main())
