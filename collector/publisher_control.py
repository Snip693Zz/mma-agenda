"""Controle du raccordement au publieur : aucun identifiant publiable n'est soumis."""
import copy
import json
import os
import re
import uuid
from collections import Counter
from pathlib import Path

RPC = 'publish_ufc_add_fights_v1'

def require(value):
    if not value:
        raise ValueError('Controle de securite non satisfait')

def control(client, report, journal):
    require(isinstance(report, dict) and report.get('mode') == 'read_only')
    require(report.get('database_read') is True and report.get('errors') == [] and report.get('published') == [])
    require(all(report.get(k) is False for k in ('database_writes','fallback_writes','automatic_publication')))
    require(journal.get('status') in ('recorded','already_recorded') and journal.get('agenda_writes') is False)
    receipt = journal['receipt']
    require(receipt.get('agenda_writes') is False)
    run_id = str(uuid.UUID(receipt['run_id']))
    require(re.fullmatch('[0-9a-f]{64}', receipt.get('report_sha256','')))
    rows = client.table('ingest_runs').select('id,status,source_sha256,extra').eq('id',run_id).execute().data
    require(isinstance(rows,list) and len(rows) == 1)
    run = rows[0]
    require(run['id'] == run_id and run['status'] == 'success' and run['source_sha256'] == receipt['report_sha256'])
    require(run['extra']['report'] == report)
    proposals = []
    offset = 0
    while True:
        batch = client.table('proposals').select('id,kind,status,event_id,ingest_run_id').eq('ingest_run_id',run_id).order('id').range(offset,offset+499).execute().data
        require(isinstance(batch,list))
        require(all(p['ingest_run_id'] == run_id for p in batch))
        proposals.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    probe = client.rpc(RPC, {'p_proposal_id': None}).execute().data
    require(isinstance(probe,dict) and probe.get('status') == 'disabled' and probe.get('agenda_writes') is False and probe.get('journal_writes') is False)
    return {'status':'disabled_verified','mode':'publisher_control_only','run_id':run_id,'report_sha256':receipt['report_sha256'],'proposals':dict(Counter(p['kind'] for p in proposals)),'probe':copy.deepcopy(probe),'agenda_writes':False,'journal_writes':False,'fallback_writes':False}

def main():
    result = {'status':'failed','mode':'publisher_control_only','agenda_writes':False,'journal_writes':False,'fallback_writes':False}
    try:
        from supabase import create_client
        report = json.loads(Path('reports/daily-refresh.json').read_text(encoding='utf-8'))
        journal = json.loads(Path('reports/journal-receipt.json').read_text(encoding='utf-8'))
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        require(url == 'https://wxrxjwfktdviiasixupk.supabase.co' and key)
        result = control(create_client(url,key),report,journal)
    except Exception as error:
        result['exception_type'] = type(error).__name__
        code = getattr(error,'code',None)
        if isinstance(code,str) and re.fullmatch('[A-Z0-9]{5,8}',code):
            result['error_code'] = code
    target = Path('reports/publisher-control.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'publisher_control':result['status'],'agenda_writes':False}))
    return 0 if result['status'] == 'disabled_verified' else 1

if __name__ == '__main__':
    raise SystemExit(main())
