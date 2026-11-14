"""Tests du collecteur PFL de rapprochement."""
from pfl_reconciliation import extract_event_date, extract_fights, reconcile_event


HTML = """
<html><body>
<h1>PFL Lyon</h1>
<p>Fight Card</p>
<p>19 décembre 2026</p>
<div>Boris Atangana vs. Bryan Battle</div>
<div>Denis Goltsov vs. Test Opponent</div>
</body></html>
"""

EVENT = {'id': 'pfl-lyon', 'title': 'PFL Lyon', 'date': '2026-12-19', 'url': 'https://pflmma.com/event/test', 'official': True}


def test_extract_fights_finds_pairs():
    fights = extract_fights(HTML)
    assert len(fights) == 2
    assert fights[0]['fighter_a'] == 'Boris Atangana'
    assert fights[0]['fighter_b'] == 'Bryan Battle'


def test_extract_event_date_parses_french_date():
    assert extract_event_date(HTML) == '2026-12-19'


def test_valid_source_creates_add_proposals():
    report = reconcile_event(EVENT, [], HTML)
    assert report['source_validation']['can_reconcile'] is True
    assert report['summary']['add_fight'] == 2
    assert all(proposal['auto_publishable'] for proposal in report['proposals'])


def test_missing_date_blocks_all_proposals():
    report = reconcile_event(EVENT, [], HTML.replace('19 décembre 2026', ''))
    assert report['source_validation']['reason'] == 'missing_or_invalid_date'
    assert report['proposals'] == []


def test_wrong_date_blocks_all_proposals():
    report = reconcile_event(EVENT, [], HTML.replace('19 décembre 2026', '19 décembre 2025'))
    assert report['source_validation']['reason'] == 'event_date_mismatch'
    assert report['proposals'] == []


def test_missing_title_blocks_all_proposals():
    report = reconcile_event(EVENT, [], HTML.replace('PFL Lyon', 'Autre événement'))
    assert report['source_validation']['reason'] == 'event_identity_unverified'
    assert report['proposals'] == []


def test_missing_card_structure_blocks_all_proposals():
    report = reconcile_event(EVENT, [], HTML.replace('Fight Card', ''))
    assert report['source_validation']['reason'] == 'card_structure_unverified'
    assert report['proposals'] == []


def test_zero_fights_blocks_all_proposals():
    report = reconcile_event(EVENT, [], HTML.replace('Boris Atangana vs. Bryan Battle', '').replace('Denis Goltsov vs. Test Opponent', ''))
    assert report['source_validation']['reason'] == 'no_exploitable_fights'
    assert report['proposals'] == []


def test_existing_fight_is_not_duplicated():
    existing = [{'fighter_a': 'Boris Atangana', 'fighter_b': 'Bryan Battle'}]
    report = reconcile_event(EVENT, existing, HTML)
    assert report['summary']['add_fight'] == 1


def test_missing_fight_is_blocked():
    existing = [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}]
    report = reconcile_event(EVENT, existing, HTML)
    assert report['summary']['blocked'] == 1
