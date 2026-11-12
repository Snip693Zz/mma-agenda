"""Journalise un rapport valide ; aucune publication dans l'agenda."""
import copy
import json
import os
import re
import uuid
from pathlib import Path

RPC = 'record_ufc_report_v1'

def record(client, report):
    if not isinstance(report, dict) or report.get('mode') != 'read_only':
        raise ValueError('Mode de rapport invalide')
    for name, expected in {'database_read': True, 'database_writes': False, 'fallback_writes': False, 'automatic_publication': False}.items():
        if report.get(name) is not expected:
            raise ValueError('Indicateur de securite invalide')
    if report.get('published') != [] or not isinstance(report.get('errors'), list) or not isinstance(report.get('entries'), list) or not report['entries']:
        raise ValueError('Structure de rapport invalide')
    if not report.get('cards_generated_at') or not report.get('generated_at'):
        raise ValueError('Horodatages manquants')
    for entry in report['entries']:
        if not isinstance(entry, dict) or entry.get('auto_publishable') is not False or entry.get('ready_to_publish') is not False or entry.get('deletions_allowed') is not False or entry.get('requires_review') is not True:
            raise ValueError('Proposition non protegee')
    receipt = client.rpc(RPC, {'p_report': copy.deepcopy(report)}).execute().data
    if not isinstance(receipt, dict) or receipt.get('agenda_writes') is not False or type(receipt.get('already_recorded')) is not bool:
        raise ValueError('Recu serveur invalide')
    uuid.UUID(receipt['run_id'])
    if not re.fullmatch('[0-9a-f]{64}', receipt.get('report_sha256', '')):
        raise ValueError('Empreinte serveur invalide')
    return {'status': 'already_recorded' if receipt['already_recorded'] else 'recorded', 'agenda_writes': False, 'receipt': receipt}

def main():
    output = {'status': 'failed', 'agenda_writes': False}
    try:
        from supabase import create_client
        raw = Path('reports/daily-refresh.json').read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError('Rapport trop volumineux')
        report = json.loads(raw)
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        if url != 'https://wxrxjwfktdviiasixupk.supabase.co' or not key:
            raise ValueError('Configuration inattendue')
        output = record(create_client(url, key), report)
    except Exception as error:
        output['exception_type'] = type(error).__name__
    target = Path('reports/journal-receipt.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'journal_status': output['status'], 'agenda_writes': False}))
    return 1 if output['status'] == 'failed' else 0

if __name__ == '__main__':
    raise SystemExit(main())
