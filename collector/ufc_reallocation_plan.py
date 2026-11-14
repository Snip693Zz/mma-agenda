"""Plan de reclassement UFC pur : aucun réseau, aucune écriture."""
import copy
import datetime as dt
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def pair(a,b):
    if any(not isinstance(n,str) or not n.strip() for n in (a,b)):
        raise ValueError('Noms invalides')
    names=tuple(sorted(unicodedata.normalize('NFC',' '.join(n.split())).casefold() for n in (a,b)))
    if names[0]==names[1]:
        raise ValueError('Combattants identiques')
    return names

def plan_reallocation(event,details):
    result={'mode':'reallocation_preview','database_writes':False,'automatic_publication':False,'status':'blocked','actions':[],'issues':[]}
    try:
        if details.get('status')!='parsed' or details.get('mode')!='details_read_only' or details.get('issues')!=[] or details.get('database_writes') is not False or details.get('automatic_publication') is not False:
            raise ValueError('Extraction non admissible')
        address=details['source_url']
        p=urlsplit(address)
        if p.scheme!='https' or p.hostname!='www.ufc.com' or p.username or p.password or p.port not in (None,443) or p.query or p.fragment or not re.fullmatch('/event/[a-zA-Z0-9-]+',p.path):
            raise ValueError('Source officielle invalide')
        if event.get('org')!='UFC' or address not in (event.get('url'),event.get('official_card_url')) or not event.get('id'):
            raise ValueError('Identité de soirée incohérente')
        if not re.fullmatch('[a-f0-9]{64}',details.get('source_sha256','')):
            raise ValueError('Empreinte source absente')
        patch=details['event_patch']
        if patch.get('date')!=event.get('event_date'):
            raise ValueError('Changement de date hors périmètre')
        if any(not isinstance(patch.get(k),str) or not patch[k].strip() for k in ('title','place')):
            raise ValueError('Métadonnées incomplètes')
        projected=copy.deepcopy(event)
        actions=[]
        changes={k:patch[k] for k in ('title','place') if event.get(k)!=patch[k]}
        if changes:
            actions.append({'operation':'update_event','values':changes})
            projected.update(changes)
        old={}; positions=set()
        for card in projected['cards']:
            pos=card['position']
            if type(pos) is not int or pos<0 or pos in positions or card.get('event_id')!=event['id']:
                raise ValueError('Identité de carte invalide')
            positions.add(pos)
            slots=set()
            for fight in card['fights']:
                if card.get('is_active') is False:
                    raise ValueError('Combats archivés présents : révision nécessaire')
                if fight.get('event_id')!=event['id'] or fight.get('card_position')!=pos or type(fight.get('position')) is not int or fight['position']<0 or fight['position'] in slots:
                    raise ValueError('Position de combat invalide')
                slots.add(fight['position'])
                key=pair(fight['fighter_a'],fight['fighter_b'])
                if key in old:
                    raise ValueError('Combat existant dupliqué')
                old[key]=fight
        observed={}; labels=set()
        for card in details['cards']:
            name=card['name']
            if name not in ('Premiers préliminaires','Préliminaires','Carte principale') or name in labels or card.get('level')!='official' or card.get('source')!=address:
                raise ValueError('Carte observée invalide')
            labels.add(name)
            if card.get('start') is not None:
                instant=dt.datetime.fromisoformat(card['start'].replace('Z','+00:00'))
                if instant.utcoffset() is None:
                    raise ValueError('Horaire sans fuseau')
            for index,names in enumerate(card['fights']):
                if not isinstance(names,list) or len(names)!=2:
                    raise ValueError('Combat observé invalide')
                key=pair(*names)
                if key in observed:
                    raise ValueError('Combat observé dupliqué')
                observed[key]=(name,index)
        if not old or set(old)!=set(observed):
            raise ValueError('Liste des combats divergente : aucun ajout ni retrait autorisé')
        next_position=max(positions,default=-1)+1
        desired={}
        for source in details['cards']:
            candidates=[c for c in projected['cards'] if c.get('is_active') is not False and c['name']==source['name'] and c.get('source')==address and c.get('extra',{}).get('allocation')!='unassigned']
            if len(candidates)>1:
                raise ValueError('Carte cible ambiguë')
            if candidates:
                target=candidates[0]
            else:
                target={'event_id':event['id'],'position':next_position,'name':source['name'],'start_at':source['start'],'level':'official','source':address,'extra':{},'is_active':True,'fights':[]}
                next_position+=1
                projected['cards'].append(target)
                actions.append({'operation':'create_card','card':{k:copy.deepcopy(v) for k,v in target.items() if k!='fights'}})
            desired[source['name']]=target
            values={k:v for k,v in {'start_at':source['start'],'level':'official'}.items() if target.get(k)!=v}
            if target.get('start_at') and source['start'] is None:
                raise ValueError('Horaire existant non retrouvé : blocage')
            if values:
                target.update(values)
                actions.append({'operation':'update_card','position':target['position'],'values':values})
        moves=[]
        for key,fight in old.items():
            name,index=observed[key]
            dest=desired[name]['position']
            if (fight['card_position'],fight['position'])!=(dest,index):
                moves.append({'operation':'move_fight','from_card':fight['card_position'],'from_position':fight['position'],'to_card':dest,'to_position':index,'fighters':[fight['fighter_a'],fight['fighter_b']]})
        actions.extend(moves)
        for card in projected['cards']:
            card['fights']=[]
        for key,fight in old.items():
            name,index=observed[key]
            moved=copy.deepcopy(fight)
            moved.update(card_position=desired[name]['position'],position=index)
            desired[name]['fights'].append(moved)
        for card in projected['cards']:
            card['fights'].sort(key=lambda f:f['position'])
            if card.get('is_active') is not False and not card['fights'] and card.get('extra',{}).get('allocation')=='unassigned':
                card['is_active']=False
                actions.append({'operation':'deactivate_empty_unassigned_card','position':card['position']})
        result.update(status='ready' if actions else 'unchanged',event_id=event['id'],baseline_sha256=digest(event),details_sha256=digest(details),source_sha256=details['source_sha256'],actions=actions,projected_event=projected,preserved_fights=len(old))
    except (KeyError,TypeError,ValueError,AttributeError) as error:
        result.update(status='blocked',actions=[],issues=[str(error)])
    return result
