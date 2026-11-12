import copy, hashlib, json
from pathlib import Path
EXPECTED={'app.js':'01c5d18132abbff44bccdb5a2f5122d77777174f','mma-data.json':'c31d789ec3c9282c4ca8af775fd6dd21aa310e42','tests/agenda.spec.cjs':'a5d60a138a80f3d52302433924a5200f4cd6ba65','tests/timing-null.spec.cjs':'0f64201e75f454a4d72886bfbd2ed93d1ccb836e'}
FIGHTS=[['Israel Adesanya','Shara Magomedov'],['Ian Machado Garry','Yaroslav Amosov'],['Serghei Spivac','Mario Pinto'],['Levan Chokheli','Islam Dulatov'],['Mairon Santos','Akbar Abdullaev'],['Magomed Tuchalov','Ion Cutelaba'],['Bruno Silva','Jafel Filho'],['Uran Satybaldiev','Ivan Gnizditskiy'],['Marco Tulio','JunYong Park'],['Pavel Andrusca','Mahammadali Osmanli'],['Modestino Rodrigues','Matthieu Duclos'],['Abdul Hussein','Hecher Sosa']]
NOTE='Horaires vérifiés le 12/11/2026 sur https://www.ufc.com/event/ufc-fight-night-december-05-2026 : préliminaires à 16 h et carte principale à 19 h, heure de Paris, le 05/12/2026. Aucun horaire séparé de premiers préliminaires n’est confirmé. Douze combats relevés sur la fiche officielle UFC le 12/11/2026 sont affichés dans une liste générale : leur répartition entre préliminaires et carte principale n’est pas établie par ce relevé. Aucun horaire individuel n’est déduit de l’ordre de la liste. Les palmarès absents restent à vérifier.'
def build_data(old):
 data=copy.deepcopy(old)
 target=[e for e in data['events'] if e['id']=='ufc-saudi']
 if len(target)!=1: raise RuntimeError('Événement absent ou ambigu')
 e=target[0]
 if e['date']!='2026-12-05' or len(e['cards'])!=3 or any(c['fights'] for c in e['cards']): raise RuntimeError('Fiche déjà modifiée')
 e['cards'].append({'source_url':'https://www.ufc.com/event/ufc-fight-night-december-05-2026','observed_on':'2026-11-12','allocation':'unassigned','order_note':'Ordre de la fiche source, sans déduction de chronologie ni horaire individuel.','name':'Combats officiels — répartition à confirmer','start':None,'level':'official','source':'UFC — fiche officielle du 12/11/2026','fights':copy.deepcopy(FIGHTS)})
 e['note']=NOTE
 assert data['fighterRecords']==old['fighterRecords']
 assert [x for x in data['events'] if x['id']!='ufc-saudi']==[x for x in old['events'] if x['id']!='ufc-saudi']
 assert e['cards'][:3]==target_original(old)['cards']
 assert sum(len(c['fights']) for x in data['events'] for c in x['cards'])==61
 return data
def target_original(old): return next(e for e in old['events'] if e['id']=='ufc-saudi')
def main():
 files={}
 for name,expected in EXPECTED.items():
  raw=Path(name).read_bytes()
  if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=expected: raise RuntimeError('Empreinte modifiée : '+name)
  files[name]=raw.decode('utf-8')
 old=json.loads(files['mma-data.json']);data=build_data(old)
 prefix="'use strict';\nconst INITIAL="
 app=files['app.js']
 if not app.startswith(prefix): raise RuntimeError('En-tête inattendu')
 initial,end=json.JSONDecoder().raw_decode(app[len(prefix):])
 if initial!=old: raise RuntimeError('Copies de secours divergentes')
 packed=json.dumps(data,ensure_ascii=False,separators=(',',':'))
 files['mma-data.json']=packed;files['app.js']=prefix+packed+app[len(prefix)+end:]
 for name,count in [('tests/agenda.spec.cjs',2),('tests/timing-null.spec.cjs',1)]:
  old_assert="toHaveText('49')"
  if files[name].count(old_assert)!=count: raise RuntimeError('Assertions inattendues : '+name)
  files[name]=files[name].replace(old_assert,"toHaveText('61')")
 marker="expect(text).not.toContain('UID:ufc-saudi-0@');"
 if files['tests/timing-null.spec.cjs'].count(marker)!=1: raise RuntimeError('Assertion export absente')
 files['tests/timing-null.spec.cjs']=files['tests/timing-null.spec.cjs'].replace(marker,marker+"expect(text).not.toContain('UID:ufc-saudi-3@');")
 files['tests/timing-null.spec.cjs']+='\n'+Path('maintenance/saudi-fallback-tests.cjs').read_text(encoding='utf-8')
 for name,text in files.items(): Path(name).write_text(text,encoding='utf-8')
 print(json.dumps({'events':len(data['events']),'fights':61,'fighter_profiles':len(data['fighterRecords']),'supabase_writes':False,'modified_files':list(files)}))
if __name__=='__main__': main()
