const fs = require('node:fs/promises');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {spawnSync} = require('node:child_process');
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
function python(args, input) {
  const result = spawnSync('python3', args, {input, encoding: 'utf8', timeout: 30000, maxBuffer: 2000000});
  if (result.error || result.status !== 0) throw new Error('Python diagnostic: ' + redact(String(result.error || result.stderr)).slice(0, 1000));
  return result.stdout;
}
async function main() {
  selfTest();
  python(['-m', 'unittest', 'discover', '-s', 'collector', '-p', 'test_pfl_card_structure.py']);
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
        status: 'unvalidated', structured_extraction: null,
        database_writes: false, automatic_publication: false,
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
          await page.waitForFunction(() => document.querySelectorAll('#fight_card_component .matchupRow a[href*="/fighter/"]').length >= 2,
            null, {timeout: 20000});
        } catch {report.component_wait = 'timeout_or_empty';}
        const snapshot = await page.evaluate(() => {
          const components = document.querySelectorAll('#fight_card_component');
          const component = components[0];
          return {component_count: components.length,
            html: component ? component.outerHTML : '',
            row_count: component ? component.querySelectorAll('.matchupRow').length : 0};
        });
        if (snapshot.component_count !== 1) throw new Error('Composant absent ou ambigu');
        const html = redact(snapshot.html);
        if (Buffer.byteLength(html) > 5000000) throw new Error('Composant trop volumineux');
        const filename = `event-${index}.html`;
        await fs.writeFile(`${directory}/${filename}`, html);
        report.component_source_file = filename;
        report.component_bytes = Buffer.byteLength(html);
        report.component_sha256 = createHash('sha256').update(html).digest('hex');
        report.dom_row_count = snapshot.row_count;
        report.structured_extraction = JSON.parse(python(['-c',
          'import sys,json; from collector.pfl_card_structure import extract_pairs; json.dump(extract_pairs(sys.stdin.read(), sys.argv[1]), sys.stdout)',
          urls[index]], html));
        const extraction = report.structured_extraction;
        const accepted = extraction.status === 'candidate_pairs' && extraction.pairs.length > 0 && extraction.row_count === snapshot.row_count;
        report.status = accepted ? 'extracted_unvalidated' : 'extraction_review_required';
        if (!accepted) failures++;
      } catch (error) {
        failures++;
        report.status = 'diagnostic_failed';
        report.errors.push(redact(String(error)).slice(0, 1000));
      } finally {
        report.warning = 'Paires candidates uniquement : identite, noms et sections non valides. Aucun acces Supabase. Composant complet archive apres masquage CSRF.';
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
