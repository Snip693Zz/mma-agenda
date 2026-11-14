"""Tests du collecteur PFL de rapprochement."""
from pfl_reconciliation import extract_fights, reconcile_event


HTML = """
<html><body>
<h1>PFL Lyon</h1>
<div>Boris Atangana vs. Bryan Battle</div>
<div>Denis Goltsov vs. Test Opponent</div>
</body></html>
"""


def test_extract_fights_finds_pairs():
    fights = extract_fights(HTML)
    assert len(fights) == 2
    assert fights[0]['fighter_a'] == 'Boris Atangana'
    assert fights[0]['fighter_b'] == 'Bryan Battle'


def test_new_official_fight_creates_add_proposal():
    event = {'id': 'pfl-lyon', 'title': 'PFL Lyon', 'url': 'https://pflmma.com/event/test', 'official': True}
    report = reconcile_event(event, [], HTML)
    assert report['summary']['add_fight'] == 2
    assert all(proposal['auto_publishable'] for proposal in report['proposals'])


def test_missing_fight_is_blocked():
    event = {'id': 'pfl-lyon', 'title': 'PFL Lyon', 'url': 'https://pflmma.com/event/test', 'official': True}
    existing = [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}]
    report = reconcile_event(event, existing, HTML)
    assert report['summary']['blocked'] == 1


def test_existing_fight_is_not_duplicated():
    event = {'id': 'pfl-lyon', 'title': 'PFL Lyon', 'url': 'https://pflmma.com/event/test', 'official': True}
    existing = [{'fighter_a': 'Boris Atangana', 'fighter_b': 'Bryan Battle'}]
    report = reconcile_event(event, existing, HTML)
    assert report['summary']['add_fight'] == 1
