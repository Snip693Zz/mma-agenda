"""Extraction structurelle et prudente de l'identité d'un événement PFL.

Le module ne publie rien et n'écrit pas dans la base. Il produit au mieux des
paires candidates, accompagnées d'un statut explicite pour revue humaine.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

EVENT_URL = "https://pflmma.com/event/pfl-lyon"
_BASE_URL = "https://pflmma.com/"
_FIGHTER_URL = re.compile(r"^https://pflmma\.com/fighter/[a-z0-9-]+$")
_SECTION_LABELS = {
    "main card": "main_card",
    "early card": "early_card",
    "prelim card": "early_card",
    "prelims": "early_card",
}


class _StructureParser(HTMLParser):
    """Parser minimal qui conserve le texte, les sections et les balises non fermées."""

    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self._html = html
        self.stack: List[str] = []
        self.sections: List[str] = []
        self.current_section: Optional[str] = None
        self.jsonld: List[Dict[str, Any]] = []
        self.anchor_sequence: List[Dict[str, Any]] = []
        self._in_jsonld = False
        self._jsonld_buffer: List[str] = []
        self._in_heading = False
        self._heading_tag = ""
        self._heading_buffer: List[str] = []
        self._in_anchor = False
        self._anchor_href = ""
        self._anchor_buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in self.VOID_TAGS:
            return
        self.stack.append(tag)
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buffer = []
        elif tag in {"h2", "h3", "h4"}:
            self._in_heading = True
            self._heading_tag = tag
            self._heading_buffer = []
        elif tag == "a":
            self._in_anchor = True
            self._anchor_href = attributes.get("href") or ""
            self._anchor_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID_TAGS:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            raise ValueError("malformed_html")
        if self._in_jsonld and tag == "script":
            self._in_jsonld = False
            self._handle_jsonld("".join(self._jsonld_buffer))
        elif self._in_heading and tag == self._heading_tag:
            self._in_heading = False
            self._handle_heading("".join(self._heading_buffer))
        elif self._in_anchor and tag == "a":
            self._in_anchor = False
            self.anchor_sequence.append({
                "href": self._anchor_href,
                "text": "".join(self._anchor_buffer),
                "section": self.current_section,
            })

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._jsonld_buffer.append(data)
        elif self._in_heading:
            self._heading_buffer.append(data)
        elif self._in_anchor:
            self._anchor_buffer.append(data)

    def _handle_jsonld(self, raw: str) -> None:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return
        documents = value if isinstance(value, list) else [value]
        for document in documents:
            if not isinstance(document, dict):
                continue
            graph = document.get("@graph", [])
            items = graph if isinstance(graph, list) else [document]
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "SportsEvent":
                    self.jsonld.append(item)

    def _handle_heading(self, text: str) -> None:
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        section = _SECTION_LABELS.get(normalized)
        if section:
            self.current_section = section
            self.sections.append(section)

    def validate(self) -> None:
        if self.stack:
            raise ValueError("malformed_html")


def _fighter_url(anchor: Dict[str, Any]) -> Optional[str]:
    url = anchor.get("href")
    if not isinstance(url, str):
        return None
    normalized = urljoin(_BASE_URL, url)
    if not _FIGHTER_URL.match(normalized):
        return None
    return normalized


def _event_identity(document: Dict[str, Any]) -> Tuple[bool, str]:
    required = ("name", "startDate", "url")
    if any(not document.get(field) for field in required):
        return False, "incomplete_jsonld_event"
    if document.get("url") != EVENT_URL:
        return False, "jsonld_event_mismatch"
    return True, ""


def extract_event(html: str, event_url: str = EVENT_URL) -> Dict[str, Any]:
    """Extrait l'identité et les paires candidates, sans les valider."""
    parser = _StructureParser(html)
    try:
        parser.feed(html)
        parser.close()
        parser.validate()
    except (ValueError, AssertionError):
        return {
            "status": "review_required",
            "reason": "malformed_html",
            "event_identity": {"status": "review_required"},
            "pairs": [],
        }

    if len(parser.jsonld) != 1:
        return {
            "status": "review_required",
            "reason": "missing_or_ambiguous_jsonld_event",
            "event_identity": {
                "status": "review_required",
                "reason": "missing_or_ambiguous_jsonld_event",
            },
            "pairs": [],
        }

    identity_ok, identity_reason = _event_identity(parser.jsonld[0])
    if not identity_ok:
        return {
            "status": "review_required",
            "reason": identity_reason,
            "event_identity": {
                "status": "review_required",
                "reason": identity_reason,
            },
            "pairs": [],
        }

    pairs = _build_pairs(parser.anchor_sequence)

    if not pairs:
        return {
            "status": "review_required",
            "reason": "ambiguous_fighter_pair",
            "event_identity": {"status": "candidate_event"},
            "pairs": [],
        }

    return {
        "status": "candidate_event",
        "event_identity": {"status": "candidate_event"},
        "pairs": pairs,
    }


def _build_pairs(anchors: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fighter_anchors = []
    for anchor in anchors:
        url = _fighter_url(anchor)
        if url:
            fighter_anchors.append({"url": url, "section": anchor.get("section")})

    if len(fighter_anchors) < 2 or len(fighter_anchors) % 2 != 0:
        return []

    pairs = []
    for index in range(0, len(fighter_anchors), 2):
        first = fighter_anchors[index]
        second = fighter_anchors[index + 1]
        section = first.get("section") or second.get("section") or "unassigned"
        pairs.append({
            "fighter_a_url": first["url"],
            "fighter_b_url": second["url"],
            "section": section,
        })
    return pairs
