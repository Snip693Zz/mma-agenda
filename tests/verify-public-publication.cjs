// Real public-site verification: no request mocking and no write credentials.
const fs = require('node:fs');
const { chromium } = require('@playwright/test');

(async () => {
  const site = new URL(process.env.PUBLIC_SITE_URL || '');
  if (site.protocol !== 'https:') throw new Error('PUBLIC_SITE_URL must use HTTPS');
  const publication = JSON.parse(fs.readFileSync('reports/shared-publication-result.json', 'utf8'));
  const report = JSON.parse(fs.readFileSync('reports/pfl-reconciliation.json', 'utf8'));
  const checked = [];
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(site.href, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#loadStatus')?.dataset.state === 'synced', null, { timeout: 30000 });
    await page.locator('#listBtn').click();
    for (const result of publication.results) {
      if (!['published', 'already_present'].includes(result.status)) continue;
      const entry = report.reports.find(e => e.event_id === result.event_id);
      if (!entry || !entry.observed_fights.length) throw new Error('Missing expected card');
      const state = await page.evaluate(({ id, expected }) => {
        const event = data.find(e => e.id === id);
        if (!event) return false;
        const normalize = s => s.normalize('NFC').toLocaleLowerCase().trim().replace(/\s+/g, ' ');
        const key = pair => pair.map(normalize).sort().join('\u0000');
        const actual = event.cards.flatMap(c => c.fights).map(key);
        return expected.every(f => actual.filter(k => k === key([f.fighter_a, f.fighter_b])).length === 1);
      }, { id: result.event_id, expected: entry.observed_fights });
      if (!state) throw new Error('Public card mismatch or duplicate: ' + result.event_id);
      const opened = await page.locator('#eventList [data-open]').evaluateAll((nodes, id) => {
        const node = nodes.find(n => n.dataset.open === id);
        if (!node) return false;
        node.click();
        return true;
      }, result.event_id);
      if (!opened) throw new Error('Event not visible in public list');
      await page.locator('#eventDialog').waitFor({ state: 'visible' });
      const body = await page.locator('#eventBody').innerText();
      for (const f of entry.observed_fights) {
        if (!body.includes(f.fighter_a) || !body.includes(f.fighter_b)) throw new Error('Fight missing from dialog');
      }
      checked.push(result.event_id);
      await page.keyboard.press('Escape');
    }
    if (!checked.length) throw new Error('No event eligible for public verification');
    fs.writeFileSync('reports/shared-public-verification.json', JSON.stringify({ status: 'verified', checked }, null, 2));
  } finally { await browser.close(); }
})().catch(error => {
  fs.writeFileSync('reports/shared-public-verification.json', JSON.stringify({ status: 'failed', reason: error.message }, null, 2));
  process.exitCode = 1;
});
