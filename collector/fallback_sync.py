"""Synchronise les secours uniquement apres une publication reussie."""
import hashlib
import json
import os
from pathlib import Path

def require(value):
    if not value:
        raise ValueError('Synchronisation refusee')

def control(result):
    require(isinstance(result,dict))
    require(result.get('status') == 'published')
    require(result.get('agenda_writes') is True)
    require(result.get('journal_writes') is True)
    require(isinstance(result.get('inserted_fights'),list) and result.get('inserted_fights'))
    require(isinstance(result.get('card_position'),int))
    require(isinstance(result.get('run_id'),str) and result.get('run_id'))
    require(isinstance(result.get('proposal_id'),str) and result.get('proposal_id'))
    return {'status':'ready','run_id':result['run_id'],'proposal_id':result['proposal_id'],'card_position':result['card_position'],'inserted':len(result['inserted_fights'])}

def sync(client, result, fallback_path='mma-data.json'):
    info = control(result)
    require(isinstance(fallback_path,str) and fallback_path)
    events = client.table('events').select('*').order('event_date').execute().data
    cards = client.table('event_cards').select('*').order('event_id,position').execute().data
    fights = client.table('fights').select('*').order('event_id,card_position,position').execute().data
    require(isinstance(events,list) and events)
    require(isinstance(cards,list) and cards)
    require(isinstance(fights,list) and fights)
    payload = {'generatedAt':None,'events':events,'cards':cards,'fights':fights}
    target = Path(fallback_path)
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {'status':'synced','run_id':info['run_id'],'proposal_id':info['proposal_id'],'fallback_path':fallback_path,'sha256':digest,'events':len(events),'cards':len(cards),'fights':len(fights),'previous_had_content':bool(previous)}

def main():
    result_path = Path('reports/publication-result.json')
    if not result_path.exists():
        print(json.dumps({'fallback_sync':'skipped','reason':'no_publication_result'}))
        return 0
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if result.get('status') != 'published':
        print(json.dumps({'fallback_sync':'skipped','reason':result.get('status','unknown')}))
        return 0
    from supabase import create_client
    client = create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    receipt = sync(client,result)
    Path('reports/fallback-sync.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'fallback_sync':'synced','sha256':receipt['sha256']}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
