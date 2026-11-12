import copy, hashlib, json
from pathlib import Path
EXPECTED={'app.js':'0a31f74ad1fa4058eb2d47e6fa41d916843c8f2a','mma-data.json':'2895ae1474a0a81b8655b9b69a3582a9261a5db0','supabase-sync.js':'4d37ebca45ab7a1f1e13251ef97049eeb3d8e234'}
NOTES={
'pfl-dubai':'Horaires vérifiés le 12/11/2026 sur https://pflmma.com/event/pfl-returns-to-dubai : Early Card à 15 h et carte principale à 19 h, heure de Paris, le 14/11/2026. Carte de combats à revalider : divergence entre le communiqué PFL du 27/10/2026 et la fiche événement. Les combats et palmarès déjà enregistrés sont conservés sans modification ; leur conservation ne constitue pas une nouvelle validation.',
'ufc-saudi':'Horaires vérifiés le 12/11/2026 sur https://www.ufc.com/event/ufc-fight-night-december-05-2026 : préliminaires à 16 h et carte principale à 19 h, heure de Paris, le 05/12/2026. Aucun horaire séparé de premiers préliminaires n’est confirmé : l’ancien horaire de cette rubrique est laissé non renseigné, sans supprimer la rubrique. Aucun combat n’est ajouté ni réparti automatiquement.'}
def once(text,old,new):
 if text.count(old)!=1: raise RuntimeError('Motif absent ou ambigu : '+old)
 return text.replace(old,new,1)
def main():
 source={}
 for name,expected in EXPECTED.items():
  raw=Path(name).read_bytes()
  actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  if actual!=expected: raise RuntimeError('Fichier modifié depuis validation : '+name)
  source[name]=raw.decode('utf-8')
 target=Path('tests/timing-null.spec.cjs')
 if target.exists(): raise RuntimeError('Le nouveau fichier de tests existe déjà')
 old=json.loads(source['mma-data.json']);data=copy.deepcopy(old);events={e['id']:e for e in data['events']}
 events['pfl-dubai']['cards'][0]['start']='2026-11-14T14:00:00Z'
 for card,start in zip(events['ufc-saudi']['cards'],[None,'2026-12-05T15:00:00Z','2026-12-05T18:00:00Z']): card['start']=start
 for eid,note in NOTES.items(): events[eid]['note']=note
 assert data['fighterRecords']==old['fighterRecords']
 assert [[c['fights'] for c in e['cards']] for e in data['events']]==[[c['fights'] for c in e['cards']] for e in old['events']]
 assert len(data['events'])==8 and len(data['fighterRecords'])==59
 packed=json.dumps(data,ensure_ascii=False,separators=(',',':'))
 prefix="'use strict';\nconst INITIAL="
 original=source['app.js']
 if not original.startswith(prefix): raise RuntimeError('En-tête inattendu')
 initial,end=json.JSONDecoder().raw_decode(original[len(prefix):])
 if initial!=old: raise RuntimeError('Copies de secours divergentes')
 app=prefix+packed+original[len(prefix)+end:]
 for before,after in PATCHES: app=once(app,before,after)
 app=once(app,'function status(e)',HELPER+'function status(e)')
 sync=once(source['supabase-sync.js'],"|| !c.start_at || !Number.isFinite(Date.parse(c.start_at))","|| (c.start_at !== null && (typeof c.start_at !== 'string' || !Number.isFinite(Date.parse(c.start_at))))")
 sync=once(sync,'start: new Date(c.start_at).toISOString()','start: c.start_at === null ? null : new Date(c.start_at).toISOString()')
 outputs={'app.js':app,'mma-data.json':packed,'supabase-sync.js':sync,'tests/timing-null.spec.cjs':Path('maintenance/timing-null.spec.cjs').read_text(encoding='utf-8')}
 for name,text in outputs.items(): Path(name).write_text(text,encoding='utf-8')
 print(json.dumps({'files':list(outputs),'events':8,'fights':49,'fighter_profiles':59,'database_writes':False}))
PATCHES=[
("function status(e){return `<span class=\"status ${e.official?'':'warning'}\">${e.official?'Horaire officiel · relevé source':'Horaire à confirmer'}</span>`}","function status(e){const complete=e.cards.length>0&&e.cards.every(hasCardTime);return `<span class=\"status ${e.official&&complete?'':'warning'}\">${e.official?(complete?'Horaire officiel · relevé source':'Horaires partiellement renseignés'):'Horaire à confirmer'}</span>`}"),
('e.official&&e.cards.length','e.official&&e.cards.some(hasCardTime)'),
('${timeFmt.format(new Date(c.start))}',"${hasCardTime(c)?timeFmt.format(new Date(c.start)):'Horaire non confirmé'}"),
('<span>HEURE DE PARIS</span>',"<span>${hasCardTime(c)?'HEURE DE PARIS':'À VÉRIFIER SUR LA SOURCE'}</span>"),
('${esc(dayFmt.format(new Date(c.start)))}',"${hasCardTime(c)?esc(dayFmt.format(new Date(c.start))):'Début non renseigné dans la source.'}"),
('<button data-export="${esc(e.id)}:${i}">','<button data-export="${esc(e.id)}:${i}" ${hasCardTime(c)?\'\':\'disabled aria-disabled="true" title="Horaire nécessaire pour un export calendrier"\'}>'),
("function stamp(s){return new Date(s).toISOString().replace(/[-:]/g,'').slice(0,15)+'Z'}","function stamp(s){if(!(s instanceof Date)&&!hasCardTime({start:s}))throw Error('Horaire requis pour le calendrier');return new Date(s).toISOString().replace(/[-:]/g,'').slice(0,15)+'Z'}"),
("function exportCards(entries){if(!entries.length)return notify('Aucune carte à exporter.');","function exportCards(entries){const total=entries.length;entries=entries.filter(pair=>Array.isArray(pair)&&pair[0]&&hasCardTime(pair[1]));const skipped=total-entries.length;if(!entries.length)return notify('Aucune carte avec un horaire renseigné à exporter.');"),
("notify('Copie .ics téléchargée, sans synchronisation ni rappel intégré.')","notify('Copie .ics téléchargée, sans synchronisation ni rappel intégré.'+(skipped?' '+skipped+' carte(s) sans horaire exclue(s).':''))"),
('if(!e)return;if(!e.official&&!confirm(',"if(!e)return;const card=e.cards[Number(i)];if(!Number.isInteger(Number(i))||!hasCardTime(card))return notify('Horaire non confirmé : export indisponible.');if(!e.official&&!confirm("),
('exportCards([[e,e.cards[Number(i)]]])','exportCards([[e,card]])'),
('||!Number.isFinite(Date.parse(c.start))||','||(c.start!==null&&!hasCardTime(c))||')]
HELPER=r"function hasCardTime(c){return !!c&&typeof c.start==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(c.start)&&Number.isFinite(Date.parse(c.start))}"+'\n'
if __name__=='__main__': main()
