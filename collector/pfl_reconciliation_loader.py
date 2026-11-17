"""Read the public PFL baseline without writing to the database."""
try:
    from .pfl_reconciliation_inputs import normalize_event, active_fights
except ImportError:
    from pfl_reconciliation_inputs import normalize_event, active_fights


def read_rows(query):
    rows = []
    offset = 0
    while True:
        page = query.range(offset, offset + 499).execute().data
        if not isinstance(page, list):
            raise ValueError('Invalid database response')
        rows.extend(page)
        if len(page) < 500:
            return rows
        offset += 500


def load_baseline(client, limit=0):
    if limit < 0:
        raise ValueError('Invalid event limit')
    events = read_rows(client.table('events').select('*').eq('org', 'PFL').order('id'))
    if limit:
        events = events[:limit]
    events = [normalize_event(event) for event in events]
    grouped = {}
    for event in events:
        event_id = event['id']
        cards = read_rows(client.table('event_cards').select('event_id,position,is_active').eq('event_id', event_id).order('position'))
        fights = read_rows(client.table('fights').select('event_id,card_position,position,fighter_a,fighter_b').eq('event_id', event_id).order('card_position').order('position'))
        grouped[event_id] = active_fights(cards, fights)
    return events, grouped
