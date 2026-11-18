"""Offline checks for the journal RPC and actual capture provenance."""
from copy import deepcopy
from unittest.mock import MagicMock
from pfl_reconciliation import save_report, reconcile_event


def test_save_report_uses_v2_without_mutating_report():
    report = {'mode': 'pfl_reconciliation_report', 'automatic_publication': False, 'errors': [], 'reports': [], 'events_observed': 0, 'fights_observed': 0}
    before = deepcopy(report)
    client = MagicMock()
    receipt = {'agenda_writes': False, 'automatic_publication': False, 'proposals_created': 0}
    client.rpc.return_value.execute.return_value.data = receipt
    assert save_report(client, report) == receipt
    name, arguments = client.rpc.call_args.args
    assert name == 'record_pfl_reconciliation_v2'
    assert arguments['p_report']['extra']['report'] == before
    assert arguments['p_report']['source_report'] == 'pfl_reconciliation_report'
    client.table.assert_not_called()
    assert report == before


def test_discovery_url_is_used_in_proposal_and_evidence():
    source = 'https://pflmma.com/event/pfl-lyon-2026'
    event = {'id': 'pfl-lyon', 'title': 'PFL Lyon', 'date': '2026-12-19', 'official': True, 'url': 'https://pflmma.com/event/pfl-lyon'}
    before = deepcopy(event)
    html = '<h1>PFL Lyon</h1><div id="fight_card_component"><div class="matchupRow"><a href="/fighter/alpha-test">Alpha Test</a><a href="/fighter/beta-test">Beta Test</a></div></div>'
    discovery = {'source_url': source, 'date': '2026-12-19', 'card_html': html, 'page_html': html}
    report = reconcile_event(event, [], '', discovery)
    assert report['source_validation']['can_reconcile'] is True
    assert len(report['proposals']) == 1
    proposal = report['proposals'][0]
    assert proposal['source_url'] == source
    assert proposal['evidence']['source_url'] == source
    assert event == before
