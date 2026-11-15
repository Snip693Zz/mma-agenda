"""Validation hors ligne de preuves SportsEvent PFL ; aucune ecriture."""
import re
from datetime import datetime
from urllib.parse import urlsplit


def validate_identity(events, source_url):
    result = {"status": "review_required", "reason": "", "source_url": source_url,
              "database_writes": False, "automatic_publication": False,
              "event_identity_validated": False}
    def reject(reason):
        result["reason"] = reason
        return result
    if not isinstance(source_url, str):
        return reject("invalid_source_url")
    try:
        source = urlsplit(source_url)
    except ValueError:
        return reject("invalid_source_url")
    if (source.scheme != "https" or source.netloc != "pflmma.com"
            or source.query or source.fragment
            or not re.fullmatch(r"/event/[a-zA-Z0-9-]+", source.path)):
        return reject("invalid_source_url")
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        return reject("invalid_identity_evidence")
    if len(events) != 1:
        return reject("missing_or_ambiguous_jsonld_event")
    event = events[0]
    if any(not isinstance(event.get(k), str) or not event[k].strip()
           for k in ("url", "name", "startDate")):
        return reject("incomplete_jsonld_event")
    if event["url"] != source_url:
        return reject("jsonld_event_mismatch")
    def parse(value):
        if not isinstance(value, str):
            raise ValueError("invalid_date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.strptime(value, "%Y-%m-%d"), "date_only"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", value):
            raise ValueError("invalid_date")
        return datetime.fromisoformat(value.replace("Z", "+00:00")), "offset_datetime"
    try:
        start, precision = parse(event["startDate"])
        if "endDate" in event:
            end, end_precision = parse(event["endDate"])
            if precision != end_precision:
                return reject("incomparable_date_precision")
            if end <= start:
                return reject("end_not_after_start")
    except (ValueError, TypeError, OverflowError):
        return reject("invalid_event_date")
    result.update(status="candidate_identity", reason="url_and_date_checks_only",
                  name=event["name"], startDate=event["startDate"],
                  date_precision=precision)
    if "endDate" in event:
        result["endDate"] = event["endDate"]
    return result
