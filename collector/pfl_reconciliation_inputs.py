"""Normalize database inputs before PFL reconciliation. No writes."""
from datetime import date


def normalize_event(row):
    event = dict(row)
    stored = event.get('event_date')
    legacy = event.get('date')
    if stored and legacy and stored != legacy:
        raise ValueError('Conflicting event dates')
    value = stored or legacy
    if not isinstance(value, str):
        raise ValueError('Missing event date')
    date.fromisoformat(value)
    event['date'] = value
    return event


def active_fights(cards, fights):
    states = {}
    for card in cards:
        key = (card['event_id'], card['position'])
        if key in states:
            raise ValueError('Duplicate card')
        state = card.get('is_active')
        if state is not None and not isinstance(state, bool):
            raise ValueError('Invalid card state')
        states[key] = state is not False
    selected = []
    for fight in fights:
        key = (fight['event_id'], fight['card_position'])
        if key not in states:
            raise ValueError('Fight references unknown card')
        if states[key]:
            selected.append(dict(fight))
    return selected
