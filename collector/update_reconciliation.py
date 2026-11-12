"""Rapprochement des mises à jour d'événements MMA.

Compare les combats observés sur une source avec ceux déjà enregistrés,
puis produit des propositions sûres : ajout, mise à jour, revue ou blocage.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Iterable


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def pair_key(fight: dict) -> tuple[str, str]:
    a = normalize_name(fight.get("fighter_a"))
    b = normalize_name(fight.get("fighter_b"))
    if not a or not b:
        raise ValueError("Combat incomplet : deux noms sont requis")
    return tuple(sorted((a, b)))


def _proposal(kind: str, status: str, event_id: str, source_url: str, source_kind: str, payload: dict, reason: str, auto: bool) -> dict:
    return {
        "kind": kind,
        "status": status,
        "event_id": event_id,
        "source_url": source_url,
        "source_kind": source_kind,
        "payload": payload,
        "evidence": {
            "source_url": source_url,
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "reason": reason,
        "auto_publishable": auto,
    }


def compare_event(event: dict, existing_fights: Iterable[dict], observed_fights: Iterable[dict]) -> list[dict]:
    """Compare une carte observée à la carte enregistrée."""
    event_id = str(event.get("id") or "")
    source_url = str(event.get("source_url") or event.get("url") or "")
    source_kind = str(event.get("source_kind") or "official")
    official = source_kind == "official"
    existing = {}
    for fight in existing_fights:
        existing[pair_key(fight)] = fight
    observed = {}
    for fight in observed_fights:
        observed[pair_key(fight)] = fight

    proposals = []
    for key, fight in observed.items():
        if key in existing:
            continue
        auto = official and event_id and source_url
        proposals.append(_proposal(
            "add_fight", "pending" if auto else "watch_only", event_id, source_url, source_kind,
            {"fighter_a": fight.get("fighter_a"), "fighter_b": fight.get("fighter_b"), "card_position": fight.get("card_position"), "position": fight.get("position")},
            "Nouveau combat observé sur la source officielle" if auto else "Nouveau combat observé sur une source non officielle",
            auto,
        ))
    for key, fight in existing.items():
        if key in observed:
            continue
        proposals.append(_proposal(
            "blocked", "blocked", event_id, source_url, source_kind,
            {"fighter_a": fight.get("fighter_a"), "fighter_b": fight.get("fighter_b")},
            "Combat existant absent du relevé : suppression non autorisée automatiquement",
            False,
        ))
    for key, fight in observed.items():
        current = existing.get(key)
        if not current:
            continue
        if normalize_name(current.get("fighter_a")) != normalize_name(fight.get("fighter_a")) or normalize_name(current.get("fighter_b")) != normalize_name(fight.get("fighter_b")):
            proposals.append(_proposal(
                "review_discrepancy", "pending", event_id, source_url, source_kind,
                {"current_fighter_a": current.get("fighter_a"), "current_fighter_b": current.get("fighter_b"), "observed_fighter_a": fight.get("fighter_a"), "observed_fighter_b": fight.get("fighter_b")},
                "Adversaire modifié : validation humaine requise",
                False,
            ))
    for field in ("event_date", "start_at", "title", "place"):
        current_value = event.get(field)
        observed_value = event.get("observed_" + field)
        if observed_value is not None and current_value != observed_value:
            proposals.append(_proposal(
                "update_event", "pending" if official else "watch_only", event_id, source_url, source_kind,
                {"field": field, "current_value": current_value, "proposed_value": observed_value},
                f"{field} modifié sur la source officielle" if official else f"{field} modifié sur une source non officielle",
                official,
            ))
    return proposals


def summarize(proposals: Iterable[dict]) -> dict:
    items = list(proposals)
    return {
        "total": len(items),
        "add_fight": sum(p["kind"] == "add_fight" for p in items),
        "update_event": sum(p["kind"] == "update_event" for p in items),
        "review_discrepancy": sum(p["kind"] == "review_discrepancy" for p in items),
        "blocked": sum(p["kind"] == "blocked" for p in items),
        "watch_only": sum(p["kind"] == "watch_only" for p in items),
        "auto_publishable": sum(p.get("auto_publishable") is True for p in items),
    }
