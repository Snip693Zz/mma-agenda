"""Controle du raccordement au publieur : aucun identifiant publiable n'est soumis."""
import copy
import json
import os
import re
import uuid
from collections import Counter
from pathlib import Path

RPC = 'publish_ufc_add_fights_v1'

class ControlError(ValueError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message

def require(value, stage: str, message: str):
    if not value:
        raise ControlError(stage, message)

def control(client, report, journal):
    require(isinstance(report, dict) and report.get('mode') == 'read_only', 'report', 'Mode de rapport invalide')
    require(report.get('database_read') is True and report.get('errors') == [] and report.get('published') == [], 'report', 'Rapport non protege')
    require(all(report.get(k) is False for k in ('database_writes','fallback_writes','automatic_publication')), 'report', 'Ecritures non desactivees')
    require(journal.get('status') in ('recorded','already_recorded') and journal.get('agenda_writes') is False, 'journal', 'Journal invalide')
    receipt = journal['receipt']
    require(receipt.get('agenda_writes') is False, 'journal', 'Recu non protege')
    run_id = str(uuid.UUID(receipt['run_id']))
    require(re.fullmatch('[0-9a-f]{64}', receipt.get('report_sha256','')), 'journal', 'Empreinte invalide')
    rows = client.table('ingest_runs').select('id,status,source_sha256,extra').eq('id',run_id).execute().data
    require(isinstance(rows,list) and len(rows) == 1, 'run', 'Run introuvable')
    run = rows[0]
    require(run['id'] == run_id and run['status'] == 'success' and run['source_sha256'] == receipt['report_sha256'], 'run', 'Run ou empreinte incompatible')
    require(run['extra']['report'] == report, 'run', 'Rapport local different du run')
    proposals = []
    offset = 0
    while True:
        batch = client.table('proposals').select('id,kind,status,event_id,ingest_run_id').eq('ingest_run_id',run_id).order('id').range(offset,offset+499).execute().data
        require(isinstance(batch,list), 'proposals', 'Requete propositions invalide')
        require(all(p['ingest_run_id'] == run_id for p in batch), 'proposals', 'Proposition hors run')
        proposals.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    probe = client.rpc(RPC, {'p_proposal_id': None}).execute().data
    require(isinstance(probe,dict) and probe.get('status') == 'disabled' and probe.get('agenda_writes') is False and probe.get('journal_writes') is False, 'rpc_probe', 'Sonde RPC non desactivee')
    return {'status':'disabled_verified','mode':'publisher_control_only','run_id':run_id,'report_sha256':receipt['report_sha256'],'proposals':dict(Counter(p['kind'] for p in proposals)),'probe':copy.deepcopy(probe),'agenda_writes':False,'journal_writes':False,'fallback_writes':False}

def main():
    result = {'status':'failed','mode':'publisher_control_only','agenda_writes':False,'journal_writes':False,'fallback_writes':False}
    try:
        from supabase import create_client
        report = json.loads(Path('reports/daily-refresh.json').read_text(encoding='utf-8'))
        journal = json.loads(Path('reports/journal-receipt.json').read_text(encoding='utf-8'))
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        require(url == 'https://wxrxjwfktdviiasixupk.supabase.co' and key, 'config', 'Configuration inattendue')
        result = control(create_client(url,key),report,journal)
    except ControlError as error:
        result['failed_stage'] = error.stage
        result['diagnostic'] = error.message
        result['exception_type'] = type(error).__name__
    except Exception as error:
        result['exception_type'] = type(error).__name__
        code = getattr(error,'code',None)
        if isinstance(code,str) and re.fullmatch('[A-Z0-9]{5,8}',code):
            result['error_code'] = code
        result['diagnostic'] = 'Erreur inattendue pendant le controle'
    target = Path('reports/publisher-control.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'publisher_control':result['status'],'agenda_writes':False,'failed_stage':result.get('failed_stage'),'diagnostic':result.get('diagnostic')},ensure_ascii=False))
    return 0 if result['status'] == 'disabled_verified' else 1

if __name__ == '__main__':
    raise SystemExit(main())
