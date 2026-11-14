"""Regression PFL : aucune publication ni connexion externe."""
import pytest
from pfl_reconciliation import extract_fights, reconcile_event, build_report

BANNER = '<div>PATRICK vs OMAR FACEOFF - PFL DUBAI - CO-MAIN EVENT</div>'
VALID = '<div>Boris Atangana vs. Bryan Battle</div>'
EVENT = {'id': 'pfl-test', 'title': 'PFL Test', 'url': 'https://pflmma.com/event/test', 'official': True}


@pytest.mark.parametrize('html', [BANNER, '<div>PATRICK vs OMAR FACE-OFF</div>'])
def test_promotion_is_not_a_fight(html):
    assert extract_fights(html) == []


def test_valid_pair_is_preserved():
    fights = extract_fights(VALID)
    assert len(fights) == 1
    assert fights[0]['fighter_a'] == 'Boris Atangana'
    assert fights[0]['fighter_b'] == 'Bryan Battle'


def test_banner_cannot_create_add_fight():
    report = reconcile_event(EVENT, [], BANNER)
    assert report['summary']['add_fight'] == 0
    assert report['summary']['auto_publishable'] == 0


def test_missing_existing_fight_remains_blocked():
    existing = [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}]
    report = reconcile_event(EVENT, existing, VALID)
    assert report['summary']['blocked'] == 1
    assert existing == [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}]


def test_report_never_enables_automatic_publication():
    report = build_report([EVENT], {}, fetcher=lambda url: VALID)
    assert report['automatic_publication'] is False
