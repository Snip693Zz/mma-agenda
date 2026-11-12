"""Prévalidation des ajouts de combats : aucune opération d’écriture."""
import collections
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

URL_PATTERN = r'https://www[.]ufc[.]com/event/[a-zA-Z0-9-]+'

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def stamp(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Horodatage sans fuseau')
    return result

def pairs(values):
    result = {}
    for pair in values:
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(n, str) or not n.strip() for n in pair):
            raise ValueError('Paire invalide')
        key = tuple(sorted(' '.join(unicodedata.normalize('NFC', n).casefold().split()) for n in pair))
        if key[0] == key[1] or key in result:
            raise ValueError('Paire non distincte ou dupliquee')
        result[key] = pair
    return result

def require(value, reason):
    if not value:
        raise ValueError(reason)

def plan(proposal, run, baseline, now):
    output = {'proposal_id': proposal.get('id'), 'decision': 'blocked', 'agenda_writes': False, 'requires_locked_revalidation': True}
    try:
        if proposal.get('kind') == 'watch_only':
            return {**output, 'decision': 'watch_only', 'reason': 'Aucun ajout demande'}
        require(proposal.get('kind') == 'add_fight', 'Type hors du perimetre de cette premiere version')
        require(proposal.get('status') == 'pending' and proposal.get('source_kind') == 'official', 'Statut ou provenance non admissible')
        address = proposal['source_url']
        require(re.fullmatch(URL_PATTERN, address), 'URL officielle invalide')
        require(run['id'] == proposal['ingest_run_id'] and run['status'] == 'success', 'Execution de collecte non validee')
        require(proposal['evidence']['report_sha256'] == run['source_sha256'], 'Empreinte de provenance incoherente')
        report = run['extra']['report']
        require(report.get('mode') == 'read_only' and report.get('database_read') is True and report.get('database_writes') is False and report.get('fallback_writes') is False and report.get('automatic_publication') is False and report.get('published') == [] and report.get('errors') == [], 'Rapport non admissible')
        observed_at = stamp(report['cards_generated_at'])
        require(now - dt.timedelta(hours=24) <= observed_at <= now + dt.timedelta(minutes=5), 'Observation perimee ou future')
        expiry = stamp(proposal['expires_at'])
        require(now < expiry <= observed_at + dt.timedelta(hours=24), 'Proposition expiree ou echeance incoherente')
        payload = proposal['payload']
        require(payload in report['entries'] and payload.get('type') == 'add_fights_proposal', 'Proposition absente du rapport')
        require(payload.get('source_url') == address and payload.get('existing_not_observed') == [] and payload.get('deletions_allowed') is False, 'Source ou comparaison incoherente')
        matches = [e for e in baseline['events'] if address in (e.get('url'), e.get('officialCardUrl'))]
        require(len(matches) == 1, 'Rapprochement de soiree ambigu')
        event = matches[0]
        require(event['org'] == 'UFC' and event['id'] == proposal['event_id'] == payload['existing_id'], 'Identifiant de soiree incoherent')
        require(dt.date.fromisoformat(event['date']) >= now.date(), 'Soiree deja passee')
        observed = pairs(payload['observed_fights'])
        proposed = pairs(payload['new_pairs'])
        current = pairs([pair for c in event['cards'] for pair in c['fights']])
        require(proposed and proposed.keys() <= observed.keys(), 'Ajouts non justifies')
        require(current.keys() <= observed.keys() and (observed.keys() - proposed.keys()) <= current.keys(), 'La carte a change depuis le rapport')
        remaining = proposed.keys() - current.keys()
        if not remaining:
            return {**output, 'decision': 'already_present', 'reason': 'Aucun ajout restant'}
        require(digest(event) == payload.get('existing_sha256'), 'La soiree a change depuis le rapport')
        names = [name for pair in observed for name in pair]
        require(len(names) == len(set(names)), 'Combattant annonce dans plusieurs combats')
        targets = [c for c in event['cards'] if c.get('allocation') == 'unassigned' and c.get('start') is None and c.get('level') == 'official' and address in (c.get('source'), c.get('source_url'))]
        require(len(targets) <= 1, 'Plusieurs rubriques non attribuees possibles')
        position = targets[0]['position'] if targets else max((c['position'] for c in event['cards']), default=-1) + 1
        return {**output, 'decision': 'candidate_add_fights', 'event_id': event['id'], 'expected_event_sha256': digest(event), 'target_card_position': position, 'create_unassigned_card': not bool(targets), 'append_pairs': [proposed[k] for k in sorted(remaining)], 'reason': 'Simulation uniquement : revalidation transactionnelle obligatoire avant execution'}
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return {**output, 'reason': str(error) if isinstance(error, ValueError) else 'Donnees incompletes ou invalides'}

def pending_rows(client):
    offset = 0
    while True:
        rows = client.table('proposals').select('*').eq('status', 'pending').order('id').range(offset, offset + 499).execute().data
        if not isinstance(rows, list):
            raise ValueError('Reponse invalide')
        yield from rows
        if len(rows) < 500:
            return
        offset += 500

def main():
    report = {'mode': 'publication_preview', 'agenda_writes': False, 'journal_writes': False, 'fallback_writes': False, 'entries': [], 'errors': []}
    now = dt.datetime.now(dt.timezone.utc)
    report['generated_at'] = now.isoformat()
    try:
        from supabase import create_client
        from daily_refresh_readonly import load_live
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        require(url == 'https://wxrxjwfktdviiasixupk.supabase.co' and key, 'Configuration invalide')
        client = create_client(url, key)
        baseline = load_live(client)
        runs = {}
        for proposal in pending_rows(client):
            run_id = proposal['ingest_run_id']
            if run_id not in runs:
                rows = client.table('ingest_runs').select('*').eq('id', run_id).execute().data
                require(isinstance(rows, list) and len(rows) == 1, 'Execution de collecte introuvable')
                runs[run_id] = rows[0]
            report['entries'].append(plan(proposal, runs[run_id], baseline, now))
    except Exception as error:
        report['errors'].append({'exception_type': type(error).__name__})
    report['summary'] = dict(collections.Counter(e['decision'] for e in report['entries']))
    target = Path('reports/publication-preview.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'summary': report['summary'], 'errors': len(report['errors']), 'agenda_writes': False}))
    return 1 if report['errors'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
