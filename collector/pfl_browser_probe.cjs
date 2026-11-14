const fs = require('node:fs/promises');
const {chromium} = require('@playwright/test');
const urls = ['https://pflmma.com/event/pfl-lyon', 'https://pflmma.com/event/2026-chicago2'];
const hosts = new Set(['pflmma.com', 'www.pflmma.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'code.jquery.com', 'unpkg.com']);
function safeUrl(value) {
  const u = new URL(value);
  for (const key of [...u.searchParams.keys()]) {
    if (!['id', 'event_id', 'eventId', 'page'].includes(key)) u.searchParams.set(key, '[redacted]');
  }
  u.hash = '';
  return u.toString();
}
async function main() {
  const directory = 'reports/pfl-browser-probe';
  await fs.mkdir(directory, {recursive: true});
  const browser = await chromium.launch({headless: true});
  let failures = 0;
  try {
    for (let index = 0; index < urls.length; index++) {
      const context = await browser.newContext({serviceWorkers: 'block', acceptDownloads: false});
      const page = await context.newPage();
      const report = {source_url: urls[index], collected_at: new Date().toISOString(),
        status: 'unvalidated', database_writes: false, automatic_publication: false,
        network: [], blocked: [], errors: []};
      await context.route('**/*', async route => {
        const request = route.request();
        const u = new URL(request.url());
        if (u.protocol !== 'https:' || !hosts.has(u.hostname) || request.method() !== 'GET' ||
            ['image', 'media', 'font'].includes(request.resourceType())) {
          if (report.blocked.length < 30) report.blocked.push({url: safeUrl(request.url()), method: request.method()});
          return route.abort();
        }
        return route.continue();
      });
      page.on('response', response => {
        const request = response.request();
        if (['xhr', 'fetch'].includes(request.resourceType()) && report.network.length < 40) {
          report.network.push({url: safeUrl(response.url()), status: response.status(),
            content_type: response.headers()['content-type'] || ''});
        }
      });
      page.on('pageerror', error => {if (report.errors.length < 10) report.errors.push(String(error).slice(0, 500));});
      try {
        const response = await page.goto(urls[index], {waitUntil: 'domcontentloaded', timeout: 45000});
        report.http_status = response ? response.status() : null;
        if (!response || !response.ok()) throw new Error('Navigation HTTP non reussie');
        try {
          await page.waitForFunction(() => {
            const element = document.querySelector('#fight_card_component');
            return element && element.textContent.trim().length > 50;
          }, null, {timeout: 20000});
        } catch {report.component_wait = 'timeout_or_empty';}
        report.dom = await page.evaluate(() => {
          const component = document.querySelector('#fight_card_component');
          return {component_found: !!component,
            component_html: component ? component.outerHTML.slice(0, 9000) : null,
            component_text: component ? component.textContent.trim().slice(0, 4000) : null,
            related_scripts: [...document.scripts].filter(s => !s.src && /fight_card_component|fightCard|axios|fetch\(/i.test(s.textContent))
              .slice(0, 3).map(s => s.textContent.slice(0, 5000))};
        });
        report.status = report.dom.component_text ? 'rendered_unvalidated' : 'empty_or_unavailable';
      } catch (error) {
        failures++;
        report.status = 'navigation_failed';
        report.errors.push(String(error).slice(0, 500));
      } finally {
        report.warning = 'Diagnostic seulement. Requetes non GET et ressources hors liste bloquees ; un echec peut provenir de ces restrictions.';
        await context.close();
        await fs.writeFile(`${directory}/event-${index}.json`, JSON.stringify(report, null, 2));
      }
    }
  } finally {await browser.close();}
  process.exitCode = failures ? 2 : 0;
}
main().catch(error => {console.error(error); process.exitCode = 1;});
