"""Exporte Supabase vers mma-data.json avec validation avant écriture."""
import collections, datetime as dt, json, os, sys
from pathlib import Path

def client():
    from supabase import create_client
    url=os.environ.get('SUPABASE_URL'); key=os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key: raise RuntimeError('SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis')
    return create_client(url,key)

def rows(client, table):
    out=[]; offset=0
    while True:
        part=client.table(table).select('*').range(offset,offset+999).execute().data
        if not isinstance(part,list): raise RuntimeError(f'Lecture invalide : {table}')
        out.extend(part)
        if len(part)<1000: return out
        offset+=1000

def iso(value):
    if not value: return None
    if isinstance(value,dt.datetime): return value.isoformat()
    return str(value)

def export(source_client=None):
    c=source_client if source_client is not None else client()
    events=rows(c,'events'); cards=rows(c,'event_cards'); fights=rows(c,'fights'); fighters=rows(c,'fighters')
    if not events: raise ValueError('Export vide refuse pour proteger le fichier de secours')
    active={(x['event_id'],x['position']) for x in cards if x.get('is_active',True)}
    by_card=collections.defaultdict(list)
    for f in fights:
        key=(f['event_id'],f['card_position'])
        if key in active: by_card[key].append(f)
    cards_by_event=collections.defaultdict(list)
    for x in cards:
        if x.get('is_active',True): cards_by_event[x['event_id']].append(x)
    out_events=[]
    for e in sorted(events,key=lambda x:(x.get('event_date') or '',x.get('id') or '')):
        eid=e.get('id')
        if not eid or not e.get('org') or not e.get('title') or not e.get('event_date') or not e.get('url'): raise ValueError(f'Événement incomplet : {eid}')
        cards_out=[]
        for card in sorted(cards_by_event.get(eid,[]),key=lambda x:x['position']):
            fs=sorted(by_card.get((eid,card['position']),[]),key=lambda x:x['position'])
            cards_out.append({'name':card.get('name') or 'Carte','level':card.get('level') or 'secondary','start':iso(card.get('start_at')),'fights':[[f['fighter_a'],f['fighter_b']] for f in fs],'source':card.get('source') or ''})
        out_events.append({'id':eid,'org':e['org'],'url':e['url'],'date':str(e['event_date']),'note':e.get('note') or '','cards':cards_out,'place':e.get('place') or '','title':e['title'],'boxUrl':e.get('box_url'),'official':bool(e.get('official')),'verified':str(e.get('verified')) if e.get('verified') else None,'officialCardUrl':e.get('official_card_url')})
    records={}
    for f in fighters:
        name=f.get('name')
        if not name: raise ValueError('Fiche sans nom')
        if name in records: raise ValueError(f'Fiche dupliquée : {name}')
        records[name]={'nc':f.get('nc'),'url':f.get('url') or '','note':f.get('note') or '','record':f.get('record') or '','source':f.get('source') or '','compare':f.get('compare_url'),'ncSource':f.get('nc_source')}
    data={'version':5,'events':out_events,'fighterRecords':records}
    ids=[e['id'] for e in out_events]
    if len(ids)!=len(set(ids)): raise ValueError('Identifiants d’événements dupliqués')
    for e in out_events:
        for card in e['cards']:
            for pair in card['fights']:
                if len(pair)!=2 or not all(pair): raise ValueError(f'Combat invalide dans {e["id"]}')
    return data

def main():
    data=export()
    target=Path('mma-data.json')
    previous=target.read_text(encoding='utf-8') if target.exists() else ''
    rendered=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    changed=previous!=rendered
    if changed:
        target.write_text(rendered,encoding='utf-8')
    report={'changed':changed,'events':len(data['events']),'fighters':len(data['fighterRecords']),'active_cards':sum(len(e['cards']) for e in data['events']),'active_fights':sum(len(c['fights']) for e in data['events'] for c in e['cards'])}
    Path('reports').mkdir(exist_ok=True)
    Path('reports/fallback-refresh.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
