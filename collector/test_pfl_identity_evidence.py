import unittest
from pfl_identity_evidence import validate_identity

LYON = "https://pflmma.com/event/pfl-lyon"
CHICAGO = "https://pflmma.com/event/2026-chicago2"

class IdentityEvidenceTests(unittest.TestCase):
    def event(self, url=LYON, **changes):
        value = {"url": url, "name": "PFL", "startDate": "2025-12-13"}
        value.update(changes)
        return value
    def test_lyon_date_only(self):
        r = validate_identity([self.event()], LYON)
        self.assertEqual(r["status"], "candidate_identity")
        self.assertEqual(r["date_precision"], "date_only")
        self.assertFalse(r["event_identity_validated"])
        self.assertFalse(r["automatic_publication"])
        self.assertFalse(r["database_writes"])
    def test_chicago_url_not_hardcoded(self):
        self.assertEqual(validate_identity([self.event(CHICAGO)], CHICAGO)["status"], "candidate_identity")
    def test_chicago_real_inverted_dates(self):
        e = self.event(CHICAGO, startDate="2026-10-16T23:00:00-04:00", endDate="2026-10-16T00:00:00-04:00")
        original = dict(e)
        self.assertEqual(validate_identity([e], CHICAGO)["reason"], "end_not_after_start")
        self.assertEqual(e, original)
    def test_mismatched_event(self):
        self.assertEqual(validate_identity([self.event()], CHICAGO)["reason"], "jsonld_event_mismatch")
    def test_ambiguous_events(self):
        self.assertEqual(validate_identity([self.event(), self.event()], LYON)["reason"], "missing_or_ambiguous_jsonld_event")
    def test_missing_event(self):
        self.assertEqual(validate_identity([], LYON)["reason"], "missing_or_ambiguous_jsonld_event")
    def test_incomplete_event(self):
        self.assertEqual(validate_identity([{"url": LYON}], LYON)["reason"], "incomplete_jsonld_event")
    def test_invalid_date(self):
        self.assertEqual(validate_identity([self.event(startDate="2025-02-30")], LYON)["reason"], "invalid_event_date")
    def test_naive_time(self):
        self.assertEqual(validate_identity([self.event(startDate="2025-12-13T12:00:00")], LYON)["reason"], "invalid_event_date")
    def test_mixed_precision(self):
        self.assertEqual(validate_identity([self.event(endDate="2025-12-14T00:00:00Z")], LYON)["reason"], "incomparable_date_precision")
    def test_offsets_compared_as_instants(self):
        e = self.event(startDate="2025-12-13T23:00:00-04:00", endDate="2025-12-14T02:00:00Z")
        self.assertEqual(validate_identity([e], LYON)["reason"], "end_not_after_start")
    def test_invalid_source(self):
        for url in ["https://evil.example/event/pfl-lyon", LYON+"?x=1", "http://pflmma.com/event/pfl-lyon", LYON+"#event"]:
            with self.subTest(url=url):
                self.assertEqual(validate_identity([self.event(url)], url)["reason"], "invalid_source_url")
    def test_bad_evidence_type(self):
        self.assertEqual(validate_identity([None], LYON)["reason"], "invalid_identity_evidence")
    def test_valid_offset_range(self):
        e = self.event(startDate="2025-12-13T23:00:00-04:00", endDate="2025-12-14T04:00:00Z")
        self.assertEqual(validate_identity([e], LYON)["status"], "candidate_identity")
