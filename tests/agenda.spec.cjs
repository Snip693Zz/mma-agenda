const { test, expect } = require('@playwright/test');
const seed = require('../mma-data.json');
const seedCounts = {
  events: String(seed.events.length),
  fights: String(seed.events.reduce((total, event) => total + event.cards.reduce((count, card) => count + card.fights.length, 0), 0)),
  fighters: String(Object.keys(seed.fighterRecords).length),
  list: seed.events.length,
};
const embeddedCounts = { events: '8', fights: '61', fighters: '59', list: 8 };
const paginationExtra = 450;
const base = 'http://127.0.0.1:8765';
const api = 'https://wxrxjwfktdviiasixupk.supabase.co/rest/v1/';
const todayParis = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris'}).format(new Date());
const periodCounts = events => {
  const today = todayParis();
  return {
    upcoming: events.filter(e => e.date >= today).length,
    past: events.filter(e => e.date < today).length,
  };
};
const seedPeriods = periodCounts(seed.events);
async function embeddedPeriods(page) {
  return page.evaluate(() => {
    const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris'}).format(new Date());
    const events = INITIAL.events;
    return {
      upcoming: events.filter(e => e.date >= today).length,
      past: events.filter(e => e.date < today).length,
    };
  });
}
async function expectLoadStatus(page, success) {
  const status = page.locator('#loadStatus');
  await expect(status).toHaveText(success ? 'Données synchronisées' : 'Affichage des données de secours');
  await expect(status).toHaveAttribute('data-state', success ? 'synced' : 'fallback');
  await expect(status).toHaveAttribute('role', 'status');
  await expect(status.locator('.sync-dot')).toBeVisible();
  await expect(status.locator('.sync-dot')).toHaveAttribute('aria-hidden', 'true');
  await expect(status.locator('.sync-dot')).toHaveCSS('background-color', success ? 'rgb(34, 197, 94)' : 'rgb(245, 158, 11)');
}
for (const mode of ['absent', 'invalide', 'valide']) {
  test(`Affichage mobile et JSON ${mode}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(api + '**', route => route.abort());
    if (mode === 'absent') await page.route('**/mma-data.json', route => route.fulfill({ status: 404, body: 'Absent' }));
    if (mode === 'invalide') await page.route('**/mma-data.json', route => route.fulfill({ contentType: 'application/json', body: '{"events":[{}],"fighterRecords":{}}' }));
    const expected = mode === 'valide' ? seedCounts : embeddedCounts;
    const periods = mode === 'valide' ? seedPeriods : await embeddedPeriods(page);
    await page.goto(base);
    await expect(page.locator('#calendar button[data-open]').first()).toBeVisible();
    await expect(page.locator('#nEvents')).toHaveText(expected.events);
    await expect(page.locator('#nFights')).toHaveText(expected.fights);
    await expect(page.locator('#nFighters')).toHaveText(expected.fighters);
    await expectLoadStatus(page, false);
    await expect(page.locator('#loadStatus')).toHaveAttribute('data-fallback-source', mode === 'valide' ? 'json' : 'embedded');
    await page.locator('#listBtn').click();
    await expect(page.locator('#listView')).toBeVisible();
    await expect(page.locator('#upcomingTab')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#eventList [data-open]')).toHaveCount(periods.upcoming);
    await page.locator('#historyTab').click();
    await expect(page.locator('#eventList [data-open]')).toHaveCount(periods.past);
    await page.locator('#eventList [data-open=ufc334]').click();
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
    if (mode === 'pagination') for (let i = 0; i < paginationExtra; i++) tables.fighters.push({ name: `Test pagination ${i}`, record: '', url: '', source: 'Test uniquement', note: '', extra: {} });
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
    const fallback = !success;
    const expected = fallback ? embeddedCounts : { ...seedCounts, fighters: String(Number(seedCounts.fighters) + (mode === 'pagination' ? paginationExtra : 0)) };
    const periods = success ? seedPeriods : await embeddedPeriods(page);
    expect(result.ok).toBe(success);
    await expectLoadStatus(page, success);
    await expect(page.locator('#nEvents')).toHaveText(expected.events);
    await expect(page.locator('#nFights')).toHaveText(expected.fights);
    await expect(page.locator('#nFighters')).toHaveText(expected.fighters);
    await page.locator('#listBtn').click();
    await expect(page.locator('#eventList [data-open]')).toHaveCount(periods.upcoming);
    if (success) {
      await page.locator('#historyTab').click();
      await expect(page.locator('#eventList [data-open]')).toHaveCount(periods.past);
      await expect(page.locator('#eventList')).toContainText('TEST SUPABASE');
    } else {
      await expect(page.locator('#eventList')).not.toContainText('TEST SUPABASE');
    }
    expect(requests.length).toBeGreaterThanOrEqual(mode === 'pagination' ? 5 : 4);
    expect(requests.every(r => r.method === 'GET' || (r.method === 'POST' && r.table === 'pfl_reconciliation_reports_v1'))).toBe(true);
    expect(errors).toEqual([]);
  });
}
