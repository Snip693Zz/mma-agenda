const fs = require('node:fs/promises');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

function parseArgs(argv) {
  const args = {listingUrl: 'https://pflmma.com/events', output: 'reports/pfl-browser-discovery.json', limit: 20};
  for (let index = 2; index < argv.length; index += 1) {
    if (argv[index] === '--listing-url') args.listingUrl = argv[index + 1];
    else if (argv[index] === '--output') args.output = argv[index + 1];
    else if (argv[index] === '--limit') args.limit = Number(argv[index + 1]) || 20;
  }
  return args;
}

const HOSTS = new Set(['pflmma.com', 'www.pflmma.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'code.jquery.com', 'unpkg.com']);

function allowed(value, method, body, tag) {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.port || !HOSTS.has(url.hostname)) return false;
    if (method === 'GET') return true;
    if (method !== 'POST' || url.origin !== 'https://pflmma.com' || url.pathname !== '/ajax/get_fight_card_component' || url.search) return false;
    const params = new URLSearchParams(body || '');
    return [...params].length === 2 && params.getAll('event_tag').length === 1 &&
      params.getAll('is_mobile').length === 1 && params.get('event_tag') === tag &&
      ['0', '1'].includes(params.get('is_mobile'));
  } catch {
    return false;
  }
}

function redact(value) {
  return String(value).replace(/(['"])X-CSRF-TOKEN(['"])\s*:\s*(['"])[^'"]*/gi, '$1X-CSRF-TOKEN$2$3[redacted]');
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    url.username = '';
    url.password = '';
    for (const key of [...url.searchParams.keys()]) {
      if (!['id', 'event_id', 'eventId', 'page'].includes(key)) url.searchParams.set(key, '[redacted]');
    }
    url.hash = '';
    return url.toString();
  } catch {
    return '[invalid-url]';
  }
}

function extractDate(text) {
  const match = text.match(/\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\b/i);
  if (!match) return '';
  const months = {JAN: 1, FEB: 2, MAR: 3, APR: 4, MAY: 5, JUN: 6, JUL: 7, AUG: 8, SEP: 9, OCT: 10, NOV: 11, DEC: 12};
  const month = months[match[2].toUpperCase()];
  if (!month) return '';
  const yearMatch = text.slice(match.index + match[0].length).match(/\b(20\d{2})\b/);
  if (!yearMatch) return '';
  const day = String(Number(match[3])).padStart(2, '0');
  const monthText = String(month).padStart(2, '0');
  return `${yearMatch[1]}-${monthText}-${day}`;
}

async function main() {
  const args = parseArgs(process.argv);
  const {chromium} = require('@playwright/test');
  const browser = await chromium.launch({headless: true});
  const candidates = [];
  let eventLinks = [];
  try {
    const listingContext = await browser.newContext({serviceWorkers: 'block', acceptDownloads: false});
    const listingPage = await listingContext.newPage();
    await listingContext.route('**/*', route => {
      const request = route.request();
      if (!allowed(request.url(), request.method(), request.postData(), '') || ['image', 'media', 'font'].includes(request.resourceType())) return route.abort();
      return route.continue();
    });
    const listingResponse = await listingPage.goto(args.listingUrl, {waitUntil: 'domcontentloaded', timeout: 45000});
    if (!listingResponse || !listingResponse.ok()) throw new Error('Navigation du calendrier PFL non reussie');
    eventLinks = await listingPage.evaluate(() => {
      const links = new Set();
      for (const anchor of document.querySelectorAll('a[href]')) {
        try {
          const url = new URL(anchor.href, location.origin);
          if (url.hostname.replace(/^www\./, '') !== 'pflmma.com') continue;
          const match = url.pathname.match(/^\/event\/([A-Za-z0-9-]+)\/?$/);
          if (match) links.add('https://pflmma.com/event/' + match[1]);
        } catch {}
      }
      return [...links];
    });
    await listingContext.close();
    const limited = eventLinks.slice(0, args.limit);
    for (const url of limited) {
      const tag = new URL(url).pathname.split('/').pop();
      const context = await browser.newContext({serviceWorkers: 'block', acceptDownloads: false});
      const page = await context.newPage();
      await context.route('**/*', route => {
        const request = route.request();
        if (!allowed(request.url(), request.method(), request.postData(), tag) || ['image', 'media', 'font'].includes(request.resourceType())) return route.abort();
        return route.continue();
      });
      const candidate = {source_url: url, title: '', date: '', start_at: '', pairs: [], row_count: 0, extraction_status: 'not_available'};
      try {
        const response = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 45000});
        if (!response || !response.ok()) throw new Error('Navigation PFL non reussie');
        try {
          await page.waitForFunction(() => document.querySelectorAll('#fight_card_component .matchupRow a[href*="/fighter/"]').length >= 2, null, {timeout: 20000});
        } catch {}
        const snapshot = await page.evaluate(() => {
          const component = document.querySelector('#fight_card_component');
          const meta = document.querySelector('meta[property="og:title"]');
          const heading = document.querySelector('h1') || document.querySelector('h2');
          const title = (meta && meta.content) || (heading && heading.textContent) || '';
          return {
            title: (title || '').trim(),
            text: document.body.innerText,
            html: component ? component.outerHTML : '',
            rowCount: component ? component.querySelectorAll('.matchupRow').length : 0,
          };
        });
        candidate.title = snapshot.title;
        candidate.date = extractDate(snapshot.text);
        candidate.row_count = snapshot.rowCount;
        const extraction = spawnSync('python3', [
          '-c',
          'import sys,json; from collector.pfl_card_structure import extract_pairs; json.dump(extract_pairs(sys.stdin.read(), sys.argv[1]), sys.stdout)',
          url,
        ], {input: redact(snapshot.html), encoding: 'utf8', maxBuffer: 2000000});
        if (extraction.status === 0) {
          const parsed = JSON.parse(extraction.stdout);
          candidate.pairs = parsed.pairs || [];
          candidate.extraction_status = parsed.status || 'not_available';
        }
      } catch (error) {
        candidate.error = redact(String(error)).slice(0, 500);
      } finally {
        candidates.push(candidate);
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  const metadataFound = candidates.filter(item => item.title && item.date).length;
  const report = {
    schema_version: 1,
    mode: 'pfl_browser_discovery',
    listing_url: args.listingUrl,
    generated_at: new Date().toISOString(),
    automatic_publication: false,
    database_writes: false,
    summary: {
      event_links: eventLinks.length,
      pages_fetched: candidates.length,
      metadata_found: metadataFound,
    },
    candidates,
  };
  await fs.mkdir(path.dirname(args.output), {recursive: true});
  await fs.writeFile(args.output, JSON.stringify(report, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify(report.summary));
}

main().catch(error => {
  console.error(redact(String(error)));
  process.exitCode = 1;
});
