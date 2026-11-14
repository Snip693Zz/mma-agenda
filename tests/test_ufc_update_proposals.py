"""Tests de la boucle de mise à jour titre/lieu."""
from ufc_proposals import build

def base():
    return {'events': [{'id': 'e1', 'org': 'UFC', 'title': 'UFC 300', 'date': '2026-12-01', 'place': 'Las Vegas', 'url': 'https://www.ufc.com/event/ufc-300', 'officialCardUrl': None, 'cards': [{'fights': [['A', 'B']]}]}]}

def cards():
    return {'generated_at': '2026-01-01T00:00:00Z', 'errors': [], 'events': [{'source_url': 'https://www.ufc.com/event/ufc-300', 'status': 'parsed', 'issues': [], 'fights': [{'source_kind': 'official', 'source_url': 'https://www.ufc.com/event/ufc-300', 'fighters': ['A', 'B']}]}]}

def catalog(title='UFC 300: Championship', place='Las Vegas, NV', date='2026-12-01'):
    return {'events': [{'source_url': 'https://www.ufc.com/event/ufc-300', 'source_kind': 'official', 'method': 'ufc_hero_timestamp', 'title': title, 'place': place, 'date': date}]}

def test_update_title_and_place():
    result = build(cards(), base(), catalog())
    entry = result['entries'][0]
    assert entry['type'] == 'update_event_proposal'
    assert {u['field'] for u in entry['updates']} == {'title', 'place'}
    assert entry['requires_review'] is True
    assert entry['deletions_allowed'] is False

def test_title_not_refined_is_blocked():
    result = build(cards(), base(), catalog(title='Autre titre'))
    assert result['entries'][0]['type'] == 'review_discrepancy'

def test_date_change_is_blocked():
    result = build(cards(), base(), catalog(date='2026-12-02'))
    assert result['entries'][0]['type'] == 'review_discrepancy'
    assert result['entries'][0]['reason'] == 'Changement de date à valider'

def test_unchanged_without_metadata_change():
    result = build(cards(), base(), catalog(title='UFC 300', place='Las Vegas'))
    assert result['entries'][0]['type'] == 'unchanged'
