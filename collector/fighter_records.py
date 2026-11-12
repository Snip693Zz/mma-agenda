"""Vérification des palmarès professionnels PFL en mode rapport."""
import argparse, datetime as dt, hashlib, json, os, re, unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

PFL_HOSTS = {'pflmma.com', 'www.pflmma.com'}
CONTEXT_RE = re.compile(r'(?:professional\s+record|pro\s+mma\s+record|mma\s+record|record)\s*[:\-]?\s*(\d{1,3}-\d{1,3}-\d{1,3})', re.I)

def slugify(name):
    if not isinstance(name, str) or not name.strip(): raise ValueError('Nom invalide')
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^a-z0-9]+', '-', normalized.casefold()).strip('-')
    if not slug: raise ValueError('Nom non convertible')
    return slug

def official_url(name): return 'https://pflmma.com/all-fighter/' + quote(slugify(name))

def needs_review(fighter):
    if not isinstance(fighter, dict) or fighter.get('source') != 'Fiche PFL': return False
    record = fighter.get('record')
    if not isinstance(record, str) or record.strip() in ('', '0-0-0'): return True
    return bool(re.search(r'à (confirmer|vérifier)', fighter.get('note') or '', re.I))

def extract_record(html):
    if not isinstance(html, str): return None
    match = CONTEXT_RE.search(html)
    return match.group(1) if match else None

def fetch_page(url, timeout=15):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in PFL_HOSTS or parsed.username or parsed.password:
        raise ValueError('URL PFL non autorisée')
    request = Request(url, headers={'User-Agent': 'mma-agenda-fighter-records/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200: raise ValueError(f'Réponse PFL invalide : {response.status}')
            return response.read().decode('utf-8', errors='replace')
    except HTTPError as error:
        if error.code == 404: raise ValueError('Fiche PFL introuvable (404)') from error
        raise

@dataclass
class Report:
    fighter: dict
    url: str
    record: str | None
    status: str
    reason: str = ''

    def as_proposal(self, run_id):
        return {'ingest_run_id': run_id, 'kind': 'review_discrepancy', 'status': 'pending', 'source_url': self.url, 'source_kind': 'official', 'event_id': None, 'payload': {'fighter_name': self.fighter['name'], 'current_record': self.fighter.get('record'), 'proposed_record': self.record, 'record_scope': 'professional'}, 'evidence': {'official_url': self.url, 'observed_record': self.record, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat()}, 'reason': self.reason or 'Palmarès professionnel PFL à valider avant publication', 'auto_publishable': False}

def build_report(fighters, fetcher=fetch_page):
    reports, errors, seen = [], [], {}
    for fighter in fighters:
        if not needs_review(fighter): continue
        name = fighter.get('name') or ''
        try:
            url = official_url(name)
            record = extract_record(fetcher(url))
            if record is None:
                reports.append(Report(fighter, url, None, 'needs_review', 'Palmarès contextualisé non trouvé'))
                continue
            seen.setdefault(record, []).append(name)
            reports.append(Report(fighter, url, record, 'pending', 'Palmarès professionnel PFL trouvé'))
        except (HTTPError, URLError, ValueError) as error:
            url = official_url(name) if name else ''
            reports.append(Report(fighter, url, None, 'needs_review', str(error)))
            errors.append({'fighter': name, 'url': url, 'reason': str(error)})
    for report in reports:
        record = report.record
        if record and len(seen.get(record, [])) > 1:
            report.status = 'needs_review'
            report.reason = 'Palmarès identique pour plusieurs combattants : extraction non fiable'
    return reports, errors

def supabase_client():
    from supabase import create_client
    url, key = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key: raise RuntimeError('SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis')
    return create_client(url, key)

def save_report(client, reports, errors):
    source = json.dumps([r.as_proposal('pending') for r in reports], ensure_ascii=False, sort_keys=True)
    run = client.table('ingest_runs').insert({'status': 'success' if not errors else 'failed', 'source_report': 'pfl_fighter_records_report', 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'events_observed': len(reports), 'fights_observed': 0, 'errors': len(errors), 'extra': {'scope': 'pfl_fighter_records', 'errors': errors}}).execute().data[0]
    run_id = run['id']
    proposals = [r.as_proposal(run_id) for r in reports]
    if proposals: client.table('proposals').insert(proposals).execute()
    return {'ingest_run_id': run_id, 'proposals': len(proposals), 'errors': len(errors)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--output', default='reports/fighter-records.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    client = supabase_client()
    fighters = client.table('fighters').select('*').eq('source', 'Fiche PFL').execute().data or []
    selected = [f for f in fighters if needs_review(f)]
    if args.limit > 0: selected = selected[:args.limit]
    reports, errors = build_report(selected)
    result = {'mode': 'fighter_records_report', 'automatic_publication': False, 'selected': len(selected), 'reports': [{'fighter': r.fighter.get('name'), 'url': r.url, 'record': r.record, 'status': r.status, 'reason': r.reason} for r in reports], 'errors': errors}
    if args.apply: result['saved'] = save_report(client, reports, errors)
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'selected': len(selected), 'reports': len(reports), 'errors': len(errors), 'saved': result.get('saved')}, ensure_ascii=False))
    return 0

if __name__ == '__main__': raise SystemExit(main())
