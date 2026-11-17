"""Primary identity resolution for PFL events."""
from __future__ import annotations

import re
from typing import Any, Dict


def _norm(value: str) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip()).lower()


def resolve_primary_identity(event: Dict[str, Any], identity: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    title = _norm(event.get('title', ''))
    heading = _norm(identity.get('heading', ''))
    url = (event.get('source_url') or '').lower()
    matched = False
    reason = ''
    if heading and title:
        if heading == title:
            matched = True
            reason = 'exact heading match'
        elif title.startswith(heading) and len(heading) >= 3:
            matched = True
            reason = 'heading is prefix of event title'
    if not matched and evidence.get('url_contains_title'):
        matched = True
        reason = 'url contains title tokens'
    return {
        'matched': matched,
        'reason': reason,
        'confidence': 'high' if matched else 'low',
    }
