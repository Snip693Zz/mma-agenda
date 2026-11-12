"""Tests de la vérification PFL des palmarès professionnels."""
from fighter_records import build_report, extract_record, needs_review, official_url, slugify


def test_slugify_and_url():
    assert slugify("Denis Goltsov") == "denis-goltsov"
    assert official_url("Denis Goltsov") == "https://pflmma.com/all-fighter/denis-goltsov"


def test_needs_review():
    assert needs_review({"source": "Fiche PFL", "record": "0-0-0", "note": ""})
    assert needs_review({"source": "Fiche PFL", "record": "", "note": ""})
    assert not needs_review({"source": "Fiche PFL", "record": "37-9-0", "note": ""})
    assert not needs_review({"source": "Sherdog", "record": "0-0-0", "note": ""})


def test_extract_record():
    assert extract_record("<p>PFL Record: 15-4-0</p>") == "15-4-0"
    assert extract_record("Professional record 37-9-0") == "37-9-0"
    assert extract_record("Aucun palmarès") is None


def test_build_report_uses_official_pages():
    fighters = [
        {"name": "Denis Goltsov", "source": "Fiche PFL", "record": "0-0-0", "note": ""},
        {"name": "Bad Name", "source": "Fiche PFL", "record": "0-0-0", "note": ""},
    ]

    def fake_fetch(url):
        if "denis-goltsov" in url:
            return "PFL Record: 15-4-0 Professional record 37-9-0"
        raise ValueError("Page introuvable")

    reports, errors = build_report(fighters, fake_fetch)
    assert reports[0].record == "15-4-0"
    assert reports[0].status == "pending"
    assert reports[1].status == "needs_review"
    assert len(errors) == 1
    proposal = reports[0].as_proposal("run")
    assert proposal["kind"] == "review_discrepancy"
    assert proposal["auto_publishable"] is False
