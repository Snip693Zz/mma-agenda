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
