"""Tests du rapprochement des mises à jour."""
from update_reconciliation import compare_event, pair_key, summarize


def test_added_official_fight_is_auto_publishable():
    event = {"id": "pfl-lyon", "source_url": "https://pflmma.com/event", "source_kind": "official"}
    proposals = compare_event(event, [], [{"fighter_a": "Boris Atangana", "fighter_b": "Bryan Battle", "card_position": 0, "position": 0}])
    assert len(proposals) == 1
    assert proposals[0]["kind"] == "add_fight"
    assert proposals[0]["auto_publishable"] is True


def test_removed_fight_is_blocked():
    event = {"id": "pfl-lyon", "source_url": "https://pflmma.com/event", "source_kind": "official"}
    proposals = compare_event(event, [{"fighter_a": "A", "fighter_b": "B"}], [])
    assert len(proposals) == 1
    assert proposals[0]["kind"] == "blocked"
    assert proposals[0]["auto_publishable"] is False


def test_changed_opponent_requires_review():
    event = {"id": "pfl-lyon", "source_url": "https://pflmma.com/event", "source_kind": "official"}
    proposals = compare_event(event, [{"fighter_a": "A", "fighter_b": "B"}], [{"fighter_a": "A", "fighter_b": "C"}])
    assert len(proposals) == 1
    assert proposals[0]["kind"] == "review_discrepancy"
    assert proposals[0]["auto_publishable"] is False


def test_non_official_addition_is_watch_only():
    event = {"id": "pfl-lyon", "source_url": "https://example.com", "source_kind": "secondary"}
    proposals = compare_event(event, [], [{"fighter_a": "A", "fighter_b": "B"}])
    assert len(proposals) == 1
    assert proposals[0]["kind"] == "watch_only"
    assert proposals[0]["auto_publishable"] is False


def test_pair_key_is_order_independent():
    assert pair_key({"fighter_a": "A", "fighter_b": "B"}) == pair_key({"fighter_a": "B", "fighter_b": "A"})


def test_summary_counts_proposals():
    event = {"id": "pfl-lyon", "source_url": "https://pflmma.com/event", "source_kind": "official"}
    proposals = compare_event(
        event,
        [{"fighter_a": "A", "fighter_b": "B"}],
        [{"fighter_a": "A", "fighter_b": "B"}, {"fighter_a": "C", "fighter_b": "D"}],
    )
    summary = summarize(proposals)
    assert summary["total"] == 1
    assert summary["add_fight"] == 1
    assert summary["auto_publishable"] == 1
