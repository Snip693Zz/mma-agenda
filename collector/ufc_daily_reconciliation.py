"""Rapprochement quotidien UFC : lecture seule, sans écriture ni publication."""
import copy
from .ufc_reallocation_plan import plan_reallocation

STATUS_MAP = {'ready': 'reallocation_ready', 'unchanged': 'unchanged', 'blocked': 'blocked'}

def to_planner_event(live_event):
    if not isinstance(live_event, dict):
        raise ValueError('Événement Supabase invalide')
    event_id = live_event.get('id')
    if not isinstance(event_id, str) or not event_id:
        raise ValueError('Identifiant d’événement manquant')
    cards = []
    for card in live_event.get('cards') or []:
        if not isinstance(card, dict):
            raise ValueError('Carte Supabase invalide')
        position = card.get('position')
        if type(position) is not int or position < 0:
            raise ValueError('Position de carte invalide')
        fights = []
        for index, pair in enumerate(card.get('fights') or []):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError('Combat Supabase invalide')
            fights.append({'event_id': event_id, 'card_position': position, 'position': index, 'fighter_a': pair[0], 'fighter_b': pair[1]})
        cards.append({'event_id': event_id, 'position': position, 'name': card.get('name'), 'start_at': card.get('start'), 'level': card.get('level'), 'source': card.get('source'), 'extra': copy.deepcopy(card.get('extra') or {}), 'is_active': card.get('is_active', True), 'fights': fights})
    return {'id': event_id, 'org': live_event.get('org'), 'url': live_event.get('url'), 'official_card_url': live_event.get('officialCardUrl'), 'event_date': live_event.get('date'), 'title': live_event.get('title'), 'place': live_event.get('place'), 'cards': cards}

def action_counts(actions):
    counts = {}
    for action in actions or []:
        operation = action.get('operation')
        if isinstance(operation, str):
            counts[operation] = counts.get(operation, 0) + 1
    return counts

def reconcile_event(live_event, details):
    entry = {'type': 'ufc_reallocation', 'mode': 'read_only', 'database_writes': False, 'automatic_publication': False, 'requires_review': True, 'ready_to_publish': False, 'auto_publishable': False, 'status': 'blocked', 'issues': [], 'action_counts': {}}
    try:
        event = to_planner_event(live_event)
        result = plan_reallocation(event, details)
        status = STATUS_MAP.get(result.get('status'), 'blocked')
        issues = list(result.get('issues') or [])
        if status == 'blocked' and any('Aucune carte exploitable' in issue for issue in issues):
            status = 'watch_only'
        entry.update({'event_id': result.get('event_id'), 'source_url': details.get('source_url'), 'source_sha256': details.get('source_sha256'), 'baseline_sha256': result.get('baseline_sha256'), 'details_sha256': result.get('details_sha256'), 'status': status, 'issues': issues, 'action_counts': action_counts(result.get('actions')), 'preserved_fights': result.get('preserved_fights')})
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        entry.update({'status': 'blocked', 'issues': [str(error)], 'action_counts': {}, 'preserved_fights': None})
    return entry

def reconcile(baseline, details_by_url):
    if not isinstance(baseline, dict) or not isinstance(baseline.get('events'), list):
        raise ValueError('Base de référence invalide')
    if not isinstance(details_by_url, dict):
        raise ValueError('Rapports UFC invalides')
    entries = []
    for live_event in baseline['events']:
        address = live_event.get('officialCardUrl') or live_event.get('url')
        details = details_by_url.get(address)
        if details is None:
            entries.append({'type': 'ufc_reallocation', 'mode': 'read_only', 'database_writes': False, 'automatic_publication': False, 'requires_review': True, 'ready_to_publish': False, 'auto_publishable': False, 'status': 'watch_only', 'event_id': live_event.get('id'), 'source_url': address, 'issues': ['Fiche officielle UFC non fournie'], 'action_counts': {}, 'preserved_fights': None})
            continue
        entries.append(reconcile_event(live_event, details))
    summary = {}
    for entry in entries:
        summary[entry['status']] = summary.get(entry['status'], 0) + 1
    return {'mode': 'ufc_daily_reconciliation', 'database_writes': False, 'automatic_publication': False, 'entries': entries, 'summary': summary, 'errors': []}
