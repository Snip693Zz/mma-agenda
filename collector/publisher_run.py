"""Produit un resultat de publication reel, sans activer la publication."""
import json
import os
from pathlib import Path

RPCS = {'add_fight': 'publish_ufc_add_fights_v1', 'update_event': 'publish_ufc_update_event_v1', 'create_event': 'publish_ufc_create_event_v1'}

def require(value):
    if not value:
        raise ValueError('Execution refusee')

def validate(report,journal):
    require(isinstance(report,dict) and report.get('mode') == 'read_only')
    require(report.get('database_read') is True and report.get('errors') == [] and report.get('published') == [])
    require(journal.get('status') in ('recorded','already_recorded') and journal.get('agenda_writes') is False)
    require(isinstance(journal.get('receipt',{}).get('run_id'),str) and journal['receipt']['run_id'])

def eligible_proposals(client,run_id):
    rows = []
    offset = 0
    while True:
        batch = client.table('proposals').select('id,kind,status,event_id,ingest_run_id').eq('ingest_run_id',run_id).in_('kind',list(RPCS)).eq('status','pending').order('id').range(offset,offset+499).execute().data
        require(isinstance(batch,list))
        require(all(p['kind'] in RPCS and p['status'] == 'pending' and p['ingest_run_id'] == run_id for p in batch))
        rows.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return rows

def run(client,report,journal):
    validate(report,journal)
    run_id = journal['receipt']['run_id']
    proposals = eligible_proposals(client,run_id)
    results = []
    for proposal in proposals:
        response = client.rpc(RPCS[proposal['kind']],{'p_proposal_id':proposal['id']}).execute()
        result = response.data if isinstance(response.data,dict) else {}
        results.append({'proposal_id':proposal['id'],'kind':proposal['kind'],'event_id':result.get('event_id',proposal.get('event_id')),'status':result.get('status','unknown'),'agenda_writes':result.get('agenda_writes',False),'journal_writes':result.get('journal_writes',False),'card_position':result.get('card_position'),'inserted_fights':result.get('inserted_fights',[]),'applied_updates':result.get('applied_updates',[])})
    published = [r for r in results if r['status'] == 'published']
    status = 'published' if published else ('no_eligible_proposals' if not results else 'not_published')
    return {'status':status,'run_id':run_id,'mode':'publisher_run','agenda_writes':any(r.get('agenda_writes') for r in results),'journal_writes':any(r.get('journal_writes') for r in results),'results':results,'published_count':len(published)}

def main():
    result = {'status':'failed','mode':'publisher_run','agenda_writes':False,'journal_writes':False,'results':[],'published_count':0}
    try:
        from supabase import create_client
        report = json.loads(Path('reports/daily-refresh.json').read_text(encoding='utf-8'))
        journal = json.loads(Path('reports/journal-receipt.json').read_text(encoding='utf-8'))
        client = create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
        result = run(client,report,journal)
    except Exception as error:
        result['exception_type'] = type(error).__name__
    target = Path('reports/publication-result.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'publisher_run':result['status'],'published_count':result['published_count']}))
    return 0 if result['status'] in ('no_eligible_proposals','published','not_published') else 1

if __name__ == '__main__':
    raise SystemExit(main())
