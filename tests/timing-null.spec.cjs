const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),seed=require('../mma-data.json');
const base='http://127.0.0.1:8765',api='https://wxrxjwfktdviiasixupk.supabase.co/rest/v1/';
async function setup(page,mode){
 const tables={events:[],event_cards:[],fights:[],fighters:[]};
 for(const e of seed.events){tables.events.push({...e,event_date:e.date,official_card_url:e.officialCardUrl,box_url:e.boxUrl,extra:{}});e.cards.forEach((c,position)=>{tables.event_cards.push({...c,event_id:e.id,position,start_at:c.start,extra:{}});c.fights.forEach((f,i)=>tables.fights.push({event_id:e.id,card_position:position,position:i,fighter_a:f[0],fighter_b:f[1]}))})}
 for(const [name,f] of Object.entries(seed.fighterRecords))tables.fighters.push({...f,name,nc_source:f.ncSource,compare_url:f.compare,extra:{}});
 if(mode==='invalid')tables.event_cards[0].start_at='invalid';
 if(mode==='embedded')await page.route('**/mma-data.json',r=>r.fulfill({status:404,body:'Absent'}));
 await page.route(api+'**',route=>{
  if(!['supabase','invalid'].includes(mode))return route.abort();
  const headers={'access-control-allow-origin':'*','access-control-allow-headers':'apikey,prefer','access-control-allow-methods':'GET,OPTIONS','access-control-expose-headers':'content-range'};
  if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers});
  const u=new URL(route.request().url()),rows=tables[u.pathname.split('/').pop()],offset=Number(u.searchParams.get('offset')||0),limit=Number(u.searchParams.get('limit')||500),part=rows.slice(offset,offset+limit);
  return route.fulfill({contentType:'application/json',headers:{...headers,'content-range':`${part.length?offset+'-'+(offset+part.length-1):'*'}/${rows.length}`},body:JSON.stringify(part)});
 });
 await page.goto(base);
 if(['supabase','invalid'].includes(mode)){await page.addScriptTag({url:base+'/supabase-sync.js'});expect((await page.evaluate(()=>window.mmaSupabaseSync)).ok).toBe(mode==='supabase')}
 else await expect(page.locator('#loadStatus')).toContainText(mode==='embedded'?'intégrées conservées':'mma-data.json chargé');
}
for(const mode of ['embedded','json','supabase']){
 test('Affichage horaire inconnu '+mode,async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await setup(page,mode);await page.evaluate(()=>openEvent('ufc-saudi'));
  await expect(page.locator('#eventBody')).toContainText('Horaire non confirmé');await expect(page.locator('#eventBody')).not.toContainText('1970');
  await expect(page.locator('#eventBody')).toContainText('16:00');await expect(page.locator('#eventBody')).toContainText('19:00');
  await expect(page.locator('[data-export="ufc-saudi:0"]')).toBeDisabled();await expect(page.locator('[data-export="ufc-saudi:1"]')).toBeEnabled();
  await expect(page.locator('#nEvents')).toHaveText('8');await expect(page.locator('#nFights')).toHaveText('61');await expect(page.locator('#nFighters')).toHaveText('59');expect(errors).toEqual([]);
 });
 test('Export sans horaire artificiel '+mode,async({page})=>{
  await setup(page,mode);const pending=page.waitForEvent('download');await page.locator('#exportAll').click();const text=fs.readFileSync(await(await pending).path(),'utf8');
  expect((text.match(/BEGIN:VEVENT/g)||[]).length).toBe(11);expect(text).not.toContain('DTSTART:1970');expect(text).not.toContain('UID:ufc-saudi-0@');expect(text).not.toContain('UID:ufc-saudi-3@');expect(text).toContain('DTSTART:20261205T150000Z');expect(text).toContain('DTSTART:20261205T180000Z');
 });
}
test('Supabase invalide conserve le secours',async({page})=>{await setup(page,'invalid');await expect(page.locator('#loadStatus')).toContainText('données de secours conservées')});
test('Validation accepte null mais refuse les horaires malformés',async({page})=>{
 await setup(page,'json');const result=await page.evaluate(()=>{const values=[null,'',0,false,'2026-11-14','invalid'];return values.map(value=>{const x=JSON.parse(JSON.stringify(INITIAL));x.events[0].cards[0].start=value;try{validate(x);return true}catch{return false}})});expect(result).toEqual([true,false,false,false,false,false]);
});

for(const mode of ['embedded','json','supabase']){
 test('Les 12 combats officiels restent disponibles '+mode,async({page})=>{
  await setup(page,mode);
  await page.evaluate(()=>openEvent('ufc-saudi'));
  const card=page.locator('#eventBody .card').filter({hasText:'Combats officiels — répartition à confirmer'});
  await expect(card).toHaveCount(1);
  await expect(card).toContainText('Horaire non confirmé');
  await expect(card.locator('[data-export="ufc-saudi:3"]')).toBeDisabled();
  await card.locator('summary').click();
  await expect(card.locator('.bout')).toHaveCount(12);
  const expected=seed.events.find(e=>e.id==='ufc-saudi').cards[3].fights;
  for(const pair of expected)for(const name of pair)await expect(card).toContainText(name);
  await expect(page.locator('#nFights')).toHaveText('61');
  await expect(page.locator('#nFighters')).toHaveText('59');
  await expect(page.locator('[data-export="ufc-saudi:1"]')).toBeEnabled();
 });
}
test('La copie intégrée égale le JSON et conserve la répartition inconnue',async({page})=>{
 await setup(page,'embedded');
 const embedded=await page.evaluate(()=>JSON.parse(JSON.stringify(INITIAL)));
 expect(embedded).toEqual(seed);
 const e=embedded.events.find(e=>e.id==='ufc-saudi');
 expect(e.cards).toHaveLength(4);expect(e.cards[3].start).toBeNull();expect(e.cards[3].allocation).toBe('unassigned');
 expect(e.cards[3].fights).toHaveLength(12);
 expect(e.cards[1].fights).toEqual([]);expect(e.cards[2].fights).toEqual([]);
 expect(e.cards[1].start).toBe('2026-12-05T15:00:00Z');expect(e.cards[2].start).toBe('2026-12-05T18:00:00Z');
});
