"""Vérification des palmarès professionnels PFL en mode rapport.

Le script lit les fiches à contrôler dans Supabase, consulte les pages officielles
PFL, extrait un palmarès professionnel lorsque celui-ci est clairement affiché, puis
crée des propositions de révision. Il ne modifie jamais directement la table
``fighters`` : la publication reste une étape séparée, validée par l’utilisateur.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

PFL_HOSTS = {"pflmma.com", "www.pflmma.com"}
RECORD_RE = re.compile(r"\b(\d{1,3}-\d{1,3}-\d{1,3})\b")


def slugify(name: str) -> str:
    """Construit un identifiant d’URL PFL stable à partir d’un nom."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nom de combattant invalide")
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if not slug:
        raise ValueError("Nom de combattant non convertible en URL")
    return slug


def official_url(name: str) -> str:
    """Construit l’URL de fiche PFL attendue pour un combattant."""
    return f"https://pflmma.com/all-fighter/{quote(slugify(name))}"


def needs_review(fighter: dict) -> bool:
    """Sélectionne les fiches PFL dont le palmarès professionnel doit être vérifié."""
    if not isinstance(fighter, dict):
        return False
    if fighter.get("source") != "Fiche PFL":
        return False
    record = fighter.get("record")
    if not isinstance(record, str) or record.strip() in {"", "0-0-0"}:
        return True
    note = fighter.get("note") or ""
    return bool(re.search(r"à (confirmer|vérifier)", note, re.IGNORECASE))


def extract_record(html: str) -> str | None:
    """Extrait le premier palmarès professionnel clairement affiché sur une fiche PFL."""
    if not isinstance(html, str):
        return None
    match = RECORD_RE.search(html)
    return match.group(1) if match else None


def fetch_page(url: str, timeout: int = 15) -> str:
    """Télécharge une page PFL en HTTPS, sans suivre une URL non autorisée."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in PFL_HOSTS or parsed.username or parsed.password:
        raise ValueError("URL PFL non autorisée")
    request = Request(url, headers={"User-Agent": "mma-agenda-fighter-records/1.0"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"Réponse PFL invalide : {response.status}")
        return response.read().decode("utf-8", errors="replace")


@dataclass
class Report:
    fighter: dict
    url: str
    record: str | None
    status: str
    reason: str = ""

    def as_proposal(self, run_id: str) -> dict:
        evidence = {
            "official_url": self.url,
            "observed_record": self.record,
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        return {
            "ingest_run_id": run_id,
            "kind": "review_discrepancy",
            "status": "pending",
            "source_url": self.url,
            "source_kind": "official",
            "event_id": None,
            "payload": {
                "fighter_name": self.fighter["name"],
                "current_record": self.fighter.get("record"),
                "proposed_record": self.record,
                "record_scope": "professional",
            },
            "evidence": evidence,
            "reason": self.reason or "Palmarès professionnel PFL à valider avant publication",
            "auto_publishable": False,
        }


def build_report(fighters: Iterable[dict], fetcher: Callable[[str], str] = fetch_page) -> tuple[list[Report], list[dict]]:
    """Consulte les fiches PFL et produit un rapport sans écriture."""
    reports: list[Report] = []
    errors: list[dict] = []
    for fighter in fighters:
        if not needs_review(fighter):
            continue
        name = fighter.get("name") or ""
        try:
            url = official_url(name)
            record = extract_record(fetcher(url))
            if record is None:
                reports.append(Report(fighter, url, None, "needs_review", "Palmarès professionnel non trouvé sur la fiche PFL"))
            else:
                reports.append(Report(fighter, url, record, "pending", "Palmarès professionnel PFL trouvé"))
        except (URLError, ValueError) as error:
            url = official_url(name) if name else ""
            reports.append(Report(fighter, url, None, "needs_review", str(error)))
            errors.append({"fighter": name, "url": url, "reason": str(error)})
    return reports, errors


def supabase_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis")
    return create_client(url, key)


def save_report(client, reports: list[Report], errors: list[dict]) -> dict:
    """Enregistre une exécution et des propositions, sans écrire dans fighters."""
    source = json.dumps([r.as_proposal("pending") for r in reports], ensure_ascii=False, sort_keys=True)
    run = client.table("ingest_runs").insert({
        "status": "success" if not errors else "failed",
        "source_report": "pfl_fighter_records_report",
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "events_observed": len(reports),
        "fights_observed": 0,
        "errors": len(errors),
        "extra": {"scope": "pfl_fighter_records", "errors": errors},
    }).execute().data[0]
    run_id = run["id"]
    proposals = [r.as_proposal(run_id) for r in reports]
    if proposals:
        client.table("proposals").insert(proposals).execute()
    return {"ingest_run_id": run_id, "proposals": len(proposals), "errors": len(errors)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérification PFL des palmarès professionnels en mode rapport")
    parser.add_argument("--limit", type=int, default=0, help="Nombre maximal de fiches à contrôler")
    parser.add_argument("--output", default="reports/fighter-records.json")
    parser.add_argument("--apply", action="store_true", help="Crée les propositions Supabase ; ne modifie jamais fighters")
    args = parser.parse_args()

    client = supabase_client()
    response = client.table("fighters").select("*").eq("source", "Fiche PFL").execute()
    fighters = response.data or []
    selected = [fighter for fighter in fighters if needs_review(fighter)]
    if args.limit > 0:
        selected = selected[: args.limit]

    reports, errors = build_report(selected)
    result = {
        "mode": "fighter_records_report",
        "automatic_publication": False,
        "selected": len(selected),
        "reports": [
            {
                "fighter": report.fighter.get("name"),
                "url": report.url,
                "record": report.record,
                "status": report.status,
                "reason": report.reason,
            }
            for report in reports
        ],
        "errors": errors,
    }
    if args.apply:
        result["saved"] = save_report(client, reports, errors)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"selected": len(selected), "reports": len(reports), "errors": len(errors), "saved": result.get("saved")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
