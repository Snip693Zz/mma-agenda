const fs = require('node:fs/promises');
const assert = require('node:assert/strict');
const urls = ['https://pflmma.com/event/pfl-lyon', 'https://pflmma.com/event/2026-chicago2'];
const hosts = new Set(['pflmma.com', 'www.pflmma.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'code.jquery.com', 'unpkg.com']);
function allowed(value, method, body, tag) {
  const u = new URL(value);
  if (u.protocol !== 'https:' || u.username || u.password || u.port || !hosts.has(u.hostname)) return false;
  if (method === 'GET') return true;
  if (method !== 'POST' || u.origin !== 'https://pflmma.com' || u.pathname !== '/ajax/get_fight_card_component' || u.search) return false;
  const params = new URLSearchParams(body || '');
  return [...params].length === 2 && params.getAll('event_tag').length === 1 &&
    params.getAll('is_mobile').length === 1 && params.get('event_tag') === tag &&
    ['0', '1'].includes(params.get('is_mobile'));
}
function redact(value) {
  return value.replace(/(['"]X-CSRF-TOKEN['"]\s*:\s*['"])[^'"]*/gi, '$1[redacted]');
}
function selfTest() {
  const endpoint = 'https://pflmma.com/ajax/get_fight_card_component';
  const body = 'event_tag=pfl-lyon&is_mobile=0';
  assert(allowed(endpoint, 'POST', body, 'pfl-lyon'));
  assert(!allowed(endpoint, 'POST', body, '2026-chicago2'));
  assert(!allowed(endpoint, 'POST', body + '&extra=1', 'pfl-lyon'));
  assert(!allowed(endpoint, 'POST', body + '&event_tag=pfl-lyon', 'pfl-lyon'));
  assert(!allowed(endpoint.replace('get_fight_card_component', 'other'), 'POST', body, 'pfl-lyon'));
  assert(!allowed(endpoint.replace('pflmma.com', 'evil.example'), 'POST', body, 'pfl-lyon'));
  assert(!allowed(endpoint, 'DELETE', body, 'pfl-lyon'));
  assert.equal(redact("'X-CSRF-TOKEN': 'example-secret'"), "'X-CSRF-TOKEN': '[redacted]'");
}
function safeUrl(value) {
  const u = new URL(value);
  u.username = ''; u.password = '';
  for (const key of [...u.searchParams.keys()]) {
    if (!['id', 'event_id', 'eventId', 'page'].includes(key)) u.searchParams.set(key, '[redacted]');
  }
  u.hash = '';
  return u.toString();
}
async function main() {
  selfTest();
  const {chromium} = require('@playwright/test');
  const directory = 'reports/pfl-browser-probe';
  await fs.mkdir(directory, {recursive: true});
  const browser = await chromium.launch({headless: true});
  let failures = 0;
  try {
    for (let index = 0; index < urls.length; index++) {
      const tag = new URL(urls[index]).pathname.split('/').pop();
      const context = await browser.newContext({serviceWorkers: 'block', acceptDownloads: false});
      const page = await context.newPage();
      const report = {source_url: urls[index], collected_at: new Date().toISOString(),
        status: 'unvalidated', database_writes: false, automatic_publication: false,
        network: [], blocked: [], errors: []};
      await context.route('**/*', async route => {
        const request = route.request();
        if (!allowed(request.url(), request.method(), request.postData(), tag) ||
            ['image', 'media', 'font'].includes(request.resourceType())) {
          const entry = {url: safeUrl(request.url()), method: request.method()};
          if (request.method() !== 'GET') report.blocked.unshift(entry);
          else if (report.blocked.length < 30) report.blocked.push(entry);
          report.blocked = report.blocked.slice(0, 30);
          return route.abort();
        }
        return route.continue();
      });
      page.on('response', response => {
        const request = response.request();
        if (['xhr', 'fetch'].includes(request.resourceType()) && report.network.length < 40) {
          report.network.push({url: safeUrl(response.url()), method: request.method(), status: response.status(),
            content_type: response.headers()['content-type'] || ''});
        }
      });
      page.on('pageerror', error => {if (report.errors.length < 10) report.errors.push(redact(String(error)).slice(0, 500));});
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
            component_html: component ? component.outerHTML.slice(0, 14000) : null,
            component_text: component ? component.textContent.trim().slice(0, 7000) : null,
            related_scripts: [...document.scripts].filter(s => !s.src && /fight_card_component|fightCard|axios|fetch\(/i.test(s.textContent))
              .slice(0, 3).map(s => s.textContent.slice(0, 5000))};
        });
        report.status = report.dom.component_text ? 'rendered_unvalidated' : 'empty_or_unavailable';
      } catch (error) {
        failures++;
        report.status = 'navigation_failed';
        report.errors.push(redact(String(error)).slice(0, 500));
      } finally {
        report.warning = 'Diagnostic seulement. Seul POST autorise : chargement de la carte PFL pour cet evenement avec deux parametres controles. Une carte vide reste non validee.';
        await context.close();
        await fs.writeFile(`${directory}/event-${index}.json`, JSON.stringify(report,
          (key, value) => typeof value === 'string' ? redact(value) : value, 2));
      }
    }
  } finally {await browser.close();}
  process.exitCode = failures ? 2 : 0;
}
if (process.argv.includes('--self-test')) selfTest();
else main().catch(error => {console.error(redact(String(error))); process.exitCode = 1;});
