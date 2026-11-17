"""PFL reconciliation helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from collector.pfl_card_structure import extract_structured_fights
from collector.pfl_date_anomaly import detect_date_anomaly
from collector.pfl_event_identity import extract_event_identity
from collector.pfl_identity_evidence import collect_identity_evidence
from collector.pfl_primary_identity import resolve_primary_identity
from collector.pfl_publication_guardrails import evaluate_publication_guardrails


def load_discovery_candidates(path: Path) -> List[Dict[str, Any]]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    candidates = data.get('candidates', []) if isinstance(data, dict) else data
    result = []
    for c in candidates:
        if not c.get('source_url'):
            continue
        if not c.get('card_html'):
            continue
        if not c.get('date'):
            continue
        result.append(c)
    return result


def reconcile_event(event: Dict[str, Any], discovery: Dict[str, Any]) -> Dict[str, Any]:
    card_html = discovery.get('card_html') or ''
    page_html = discovery.get('page_html') or card_html
    identity = extract_event_identity(page_html, event)
    evidence = collect_identity_evidence(page_html, event)
    primary = resolve_primary_identity(event, identity, evidence)
    fights = extract_structured_fights(card_html)
    anomaly = detect_date_anomaly(event, discovery)
    guard = evaluate_publication_guardrails(event, discovery, primary, fights, anomaly)
    return {
        'event': event,
        'identity': identity,
        'identity_evidence': evidence,
        'primary_identity': primary,
        'structured_fights': fights,
        'date_anomaly': anomaly,
        'guardrails': guard,
    }


def reconcile_all(events: List[Dict[str, Any]], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for event in events:
        match = None
        for c in candidates:
            if c.get('source_url') == event.get('source_url'):
                match = c
                break
        if not match:
            continue
        results.append(reconcile_event(event, match))
    return results
