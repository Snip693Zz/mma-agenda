"""Regression checks: no historical-card alerts or invented Early Card allocation."""
from copy import deepcopy
from unittest.mock import patch
import pytest
import pfl_reconciliation as pfl


def fight(a, b, card):
    return {'event_id': 'pfl-test', 'fighter_a': a, 'fighter_b': b,
            'card_position': card, 'position': 0}


def test_only_explicitly_active_cards_are_compared():
    cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
             {'event_id': 'pfl-test', 'position': 2, 'is_active': True},
             {'event_id': 'other', 'position': 3, 'is_active': True}]
    fights = [fight('Old A', 'Old B', 0), fight('Live A', 'Live B', 2),
              fight('Orphan A', 'Orphan B', 3)]
    before = deepcopy(fights)
    assert pfl.active_card_fights('pfl-test', fights, cards) == [fights[1]]
    assert fights == before


def test_missing_active_cards_fails_closed():
    with pytest.raises(ValueError):
        pfl.active_card_fights('pfl-test', [], [])


def test_report_requires_card_metadata():
    report = pfl.build_report([{'id': 'pfl-test'}], {}, fetcher=lambda _: '')
    assert report['events_observed'] == 0
    assert len(report['errors']) == 1
    assert report['summary']['total'] == 0


def test_report_filters_history_and_preserves_unknown_allocation():
    event = {'id': 'pfl-test', 'title': 'PFL Test', 'official': True,
             'date': '2026-12-19', 'url': 'https://pflmma.com/event/pfl-test'}
    cards = [{'event_id': 'pfl-test', 'position': 0, 'is_active': False},
             {'event_id': 'pfl-test', 'position': 2, 'is_active': True}]
    existing = [fight('Old A', 'Old B', 0), fight('Live A', 'Live B', 2)]
    observed = [fight('Live A', 'Live B', 0), fight('New A', 'New B', 0)]
    with patch.object(pfl, 'extract_structured_fights', return_value=deepcopy(observed)), \
         patch.object(pfl, 'extract_event_identity', return_value=True), \
         patch.object(pfl, 'extract_event_date', return_value='2026-12-19'):
        report = pfl.build_report([event], {'pfl-test': existing}, fetcher=lambda _: '', cards=cards)
    assert not report['errors']
    assert report['summary']['total'] == 1
    proposal = report['reports'][0]['proposals'][0]
    assert proposal['kind'] == 'add_fight'
    assert proposal['payload']['card_position'] is None
    assert proposal['payload']['allocation'] == 'unassigned'
    assert proposal['auto_publishable'] is False
    assert proposal['evidence']['publication_requires_card_assignment'] is True
    assert report['summary']['auto_publishable'] == 0
    assert report['automatic_publication'] is False
    assert existing[0]['card_position'] == 0


def test_active_absence_and_opponent_change_remain_review_only():
    event = {'id': 'pfl-test', 'title': 'PFL Test', 'official': True,
             'date': '2026-12-19', 'url': 'https://pflmma.com/event/pfl-test'}
    existing = [fight('Current A', 'Same B', 2), fight('Missing A', 'Missing B', 2)]
    observed = [fight('Replacement A', 'Same B', 0)]
    with patch.object(pfl, 'extract_structured_fights', return_value=observed), \
         patch.object(pfl, 'extract_event_identity', return_value=True), \
         patch.object(pfl, 'extract_event_date', return_value='2026-12-19'):
        result = pfl.reconcile_event(event, existing, '')
    assert result['summary']['review_discrepancy'] == 1
    assert result['summary']['blocked'] == 1
    assert all(p['auto_publishable'] is False for p in result['proposals'])
