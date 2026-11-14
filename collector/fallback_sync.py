"""Synchronise les secours au format du site apres une publication reussie."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
try:
    from .export_fallback import export
except ImportError:
    from export_fallback import export

def require(value):
    if not value:
        raise ValueError('Synchronisation refusee')

def control(result):
    require(isinstance(result,dict) and result.get('mode')=='publisher_run')
    require(result.get('status')=='published' and result.get('agenda_writes') is True and result.get('journal_writes') is True)
    require(isinstance(result.get('run_id'),str) and result['run_id'])
    entries=result.get('results')
    require(isinstance(entries,list) and entries)
    ids=[];published=[]
    for item in entries:
        require(isinstance(item,dict))
        pid=item.get('proposal_id')
        require(isinstance(pid,str) and pid and pid not in ids)
        ids.append(pid)
        require(item.get('kind') in ('add_fight','update_event','create_event'))
        if item.get('status')!='published':
            require(item.get('agenda_writes') is False and item.get('journal_writes') is False)
            continue
        require(item.get('agenda_writes') is True and item.get('journal_writes') is True)
        require(isinstance(item.get('event_id'),str) and item['event_id'])
        if item['kind']=='add_fight':
            require(isinstance(item.get('inserted_fights'),list) and item['inserted_fights'])
            require(type(item.get('card_position')) is int and item['card_position']>=0)
        elif item['kind']=='create_event':
            require(isinstance(item.get('inserted_fights'),list))
        else:
            changes=item.get('applied_updates')
            require(isinstance(changes,list) and changes)
            require(all(isinstance(c,dict) and c.get('field') in ('title','place') for c in changes))
        published.append(item)
    require(published and type(result.get('published_count')) is int and result['published_count']==len(published))
    return {'status':'ready','run_id':result['run_id'],'proposal_ids':[p['proposal_id'] for p in published],'published_count':len(published)}

def sync(client,result,fallback_path='mma-data.json'):
    info=control(result)
    require(isinstance(fallback_path,str) and fallback_path)
    data=export(source_client=client)
    require(isinstance(data.get('events'),list) and data['events'])
    target=Path(fallback_path)
    previous=target.read_text(encoding='utf-8') if target.exists() else ''
    rendered=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    changed=previous!=rendered
    if changed:
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as handle:
                temporary=Path(handle.name);handle.write(rendered)
            temporary.replace(target)
        finally:
            if temporary is not None and temporary.exists(): temporary.unlink()
    return {**info,'status':'synced','changed':changed,'fallback_path':fallback_path,'sha256':hashlib.sha256(rendered.encode('utf-8')).hexdigest(),'events':len(data['events']),'cards':sum(len(e['cards']) for e in data['events']),'fights':sum(len(c['fights']) for e in data['events'] for c in e['cards']),'previous_had_content':bool(previous)}

def main():
    result_path=Path('reports/publication-result.json')
    if not result_path.exists():
        print(json.dumps({'fallback_sync':'skipped','reason':'no_publication_result'}));return 0
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if result.get('status')!='published':
        print(json.dumps({'fallback_sync':'skipped','reason':result.get('status','unknown')}));return 0
    from supabase import create_client
    client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    receipt=sync(client,result)
    Path('reports').mkdir(exist_ok=True)
    Path('reports/fallback-sync.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'fallback_sync':'synced','changed':receipt['changed'],'sha256':receipt['sha256']}))
    return 0

if __name__=='__main__': raise SystemExit(main())
