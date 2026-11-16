"""Synchronisation PFL désactivée : génère uniquement un rapport de contrôle."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()

    report = {
        "schema_version": 1,
        "mode": "fallback_guardrails",
        "database_writes": False,
        "automatic_publication": False,
        "sync_requested": bool(args.sync),
        "status": "blocked_by_guardrails",
        "auto_publishable": False,
        "requires_manual_approval": True,
        "synced_count": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reason": "La synchronisation PFL reste désactivée sans validation explicite.",
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
