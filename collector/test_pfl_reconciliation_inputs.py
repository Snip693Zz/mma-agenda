import pytest
from pfl_reconciliation_inputs import normalize_event, active_fights


def test_database_date_is_normalized_without_mutation():
    row = {'event_date': '2026-11-14'}
    assert normalize_event(row)['date'] == '2026-11-14'
    assert 'date' not in row


def test_conflicting_dates_are_rejected():
    with pytest.raises(ValueError):
        normalize_event({'event_date': '2026-11-14', 'date': '2026-11-15'})


def test_missing_date_is_rejected():
    with pytest.raises(ValueError):
        normalize_event({})


def test_inactive_fights_are_excluded():
    cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
             {'event_id': 'pfl-test', 'position': 1, 'is_active': True}]
    fights = [{'event_id': 'pfl-test', 'card_position': 0},
              {'event_id': 'pfl-test', 'card_position': 1}]
    assert active_fights(cards, fights) == [fights[1]]


def test_unknown_card_is_rejected():
    with pytest.raises(ValueError):
        active_fights([], [{'event_id': 'pfl-test', 'card_position': 0}])


def test_legacy_null_state_remains_visible():
    card = {'event_id': 'pfl-test', 'position': 0, 'is_active': None}
    fight = {'event_id': 'pfl-test', 'card_position': 0}
    assert active_fights([card], [fight]) == [fight]
