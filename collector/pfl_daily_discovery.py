"""Daily PFL discovery runner."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'pfl'


def run_browser_discovery() -> int:
    script = ROOT / 'collector' / 'pfl_browser_discovery.cjs'
    if not script.exists():
        print('browser discovery script missing', file=sys.stderr)
        return 1
    return subprocess.call(['node', str(script)], cwd=str(ROOT))


def load_candidates():
    path = ART / 'event-candidates.json'
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_report(candidates):
    now = datetime.now(timezone.utc).isoformat()
    return {
        'generated_at': now,
        'candidates': [
            {
                'source_url': c.get('source_url', ''),
                'title': c.get('title', ''),
                'heading': c.get('heading', ''),
                'section_text': c.get('section_text', ''),
                'card_html': c.get('card_html', ''),
                'page_html': c.get('page_html', ''),
            }
            for c in candidates
        ],
    }


def main() -> int:
    code = run_browser_discovery()
    if code != 0:
        return code
    candidates = load_candidates()
    report = build_report(candidates)
    out = ART / 'daily-discovery-report.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
