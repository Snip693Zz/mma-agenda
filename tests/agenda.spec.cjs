const { test, expect } = require('@playwright/test');
const seed = require('../mma-data.json');
const base = 'http://127.0.0.1:8765';
const api = 'https://wxrxjwfktdviiasixupk.supabase.co/rest/v1/';
for (const mode of ['absent', 'invalide', 'valide']) {
  test(`Affichage mobile et JSON ${mode}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(api + '**', route => route.abort());
    if (mode === 'absent') await page.route('**/mma-data.json', route => route.fulfill({ status: 404, body: 'Absent' }));
    if (mode === 'invalide') await page.route('**/mma-data.json', route => route.fulfill({ contentType: 'application/json', body: '{"events":[{}],"fighterRecords":{}}' }));
    await page.goto(base);
    await expect(page.locator('#calendar button[data-open]').first()).toBeVisible();
    await expect(page.locator('#nEvents')).toHaveText('8');
    await expect(page.locator('#nFights')).toHaveText('61');
    await expect(page.locator('#nFighters')).toHaveText('59');
    await expect(page.locator('#loadStatus')).toContainText(mode === 'valide' ? 'mma-data.json chargé' : 'intégrées conservées');
    await page.locator('#listBtn').click();
    await expect(page.locator('#listView')).toBeVisible();
    await expect(page.locator('#eventList [data-open]')).toHaveCount(8);
    await page.locator('#eventList [data-open]').first().click();
    await expect(page.locator('#eventDialog')).toBeVisible();
    await expect(page.locator('#eventBody')).toContainText('UFC 334');
    await expect(page.locator('#eventBody')).toContainText('Jared Gordon');
    await page.keyboard.press('Escape');
    await page.locator('#monthBtn').click();
    await page.locator('#next').click();
    await expect(page.locator('#monthTitle')).toContainText('décembre');
    await expect(page.locator('#calendar button[data-open]')).toHaveCount(4);
    expect(errors).toEqual([]);
  });
}
function fixtures() {
  const tables = { events: [], event_cards: [], fights: [], fighters: [] };
  for (const e of seed.events) {
    tables.events.push({ ...e, event_date: e.date, official_card_url: e.officialCardUrl, box_url: e.boxUrl, extra: {} });
    e.cards.forEach((c, position) => {
      tables.event_cards.push({ ...c, event_id: e.id, position, start_at: c.start, extra: {} });
      c.fights.forEach((f, i) => tables.fights.push({ event_id: e.id, card_position: position, position: i, fighter_a: f[0], fighter_b: f[1] }));
    });
  }
  for (const [name, f] of Object.entries(seed.fighterRecords)) tables.fighters.push({ ...f, name, nc_source: f.ncSource, compare_url: f.compare, extra: {} });
  return tables;
}
for (const mode of ['valide', 'refuse', 'incoherent', 'vide', 'pagination']) {
  test(`Synchronisation Supabase ${mode}`, async ({ page }) => {
    const tables = fixtures(), errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message));
    tables.events.find(e => e.id === 'ufc334').title = 'UFC 334 — TEST SUPABASE';
    if (mode === 'incoherent') tables.fights[0].event_id = 'evenement-inexistant';
    if (mode === 'vide') tables.events = [];
    if (mode === 'pagination') for (let i = 0; i < 450; i++) tables.fighters.push({ name: `Test pagination ${i}`, record: '', url: '', source: 'Test uniquement', note: '', extra: {} });
    await page.route('**/mma-data.json', route => route.fulfill({ status: 404, body: 'Absent' }));
    await page.route(api + '**', route => {
      const request = route.request(), url = new URL(request.url()), table = url.pathname.split('/').pop();
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'apikey,prefer', 'access-control-allow-methods': 'GET,OPTIONS' } });
      requests.push({ method: request.method(), table });
      if (mode === 'refuse') return route.fulfill({ status: 403, headers: { 'access-control-allow-origin': '*' }, body: '{}' });
      const rows = tables[table];
      if (!rows) return route.fulfill({ status: 404, body: '{}' });
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 500);
      const part = rows.slice(offset, offset + limit);
      return route.fulfill({ contentType: 'application/json', headers: { 'access-control-allow-origin': '*', 'access-control-expose-headers': 'content-range', 'content-range': `${part.length ? offset + '-' + (offset + part.length - 1) : '*'}/${rows.length}` }, body: JSON.stringify(part) });
    });
    await page.goto(base);
    await page.addScriptTag({ url: base + '/supabase-sync.js' });
    const result = await page.evaluate(() => window.mmaSupabaseSync);
    const success = ['valide', 'pagination'].includes(mode);
    expect(result.ok).toBe(success);
    await expect(page.locator('#loadStatus')).toContainText(success ? 'Supabase chargé en lecture seule' : 'données de secours conservées');
    await expect(page.locator('#nEvents')).toHaveText('8');
    await expect(page.locator('#nFights')).toHaveText('61');
    await expect(page.locator('#nFighters')).toHaveText(mode === 'pagination' ? '509' : '59');
    await page.locator('#listBtn').click();
    await expect(page.locator('#eventList [data-open]')).toHaveCount(8);
    if (success) await expect(page.locator('#eventList')).toContainText('TEST SUPABASE');
    else await expect(page.locator('#eventList')).not.toContainText('TEST SUPABASE');
    expect(requests.length).toBeGreaterThanOrEqual(mode === 'pagination' ? 5 : 4);
    expect(requests.every(r => r.method === 'GET')).toBe(true);
    expect(errors).toEqual([]);
  });
}
