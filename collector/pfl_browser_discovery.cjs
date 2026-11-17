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

function extractDate(text, eventUrl) {
  const match = text.match(/\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\b/i);
  if (!match) return {date: '', source: ''};
  const months = {JAN: 1, FEB: 2, MAR: 3, APR: 4, MAY: 5, JUN: 6, JUL: 7, AUG: 8, SEP: 9, OCT: 10, NOV: 11, DEC: 12};
  const month = months[match[2].toUpperCase()];
  if (!month) return {date: '', source: ''};
  const day = String(Number(match[3])).padStart(2, '0');
  const monthText = String(month).padStart(2, '0');
  const urlYearMatch = String(eventUrl).match(/(?:^|[-\/])(20\d{2})(?:[-/]|$)/);
  if (urlYearMatch) {
    return {date: `${urlYearMatch[1]}-${monthText}-${day}`, source: 'url_year'};
  }
  const now = new Date();
  const currentYear = now.getFullYear();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const candidate = new Date(currentYear, month - 1, Number(day));
  if (candidate >= today) {
    return {date: `${currentYear}-${monthText}-${day}`, source: 'visible_date+current_year_for_future'};
  }
  return {date: `${currentYear}-${monthText}-${day}`, source: 'current_year_for_past_date'};
}

function extractJsonLdDate(payloads, eventUrl) {
  const expectedPath = new URL(eventUrl).pathname.replace(/\/$/, '');
  for (const payload of payloads) {
    try {
      const parsed = JSON.parse(payload);
      const stack = [parsed];
      while (stack.length) {
        const item = stack.pop();
        if (!item || typeof item !== 'object') continue;
        if (Array.isArray(item)) {
          stack.push(...item);
          continue;
        }
        const types = item['@type'];
        const typeList = Array.isArray(types) ? types : [types];
        if (typeList.includes('Event')) {
          const itemUrl = String(item.url || '');
          let itemPath = '';
          try {
            itemPath = new URL(itemUrl).pathname.replace(/\/$/, '');
          } catch {}
          if (itemPath && itemPath === expectedPath && item.startDate) {
            return String(item.startDate);
          }
        }
        for (const value of Object.values(item)) {
          if (value && typeof value === 'object') stack.push(value);
        }
      }
    } catch {}
  }
  return '';
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
      const candidate = {source_url: url, title: '', date: '', start_at: '', pairs: [], row_count: 0, extraction_status: 'not_available', date_found: false, date_source: '', text_excerpt: '', jsonld_found: false, jsonld_start_date: '', card_html: '', page_html: ''};
      try {
        const response = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 45000});
        if (!response || !response.ok()) throw new Error('Navigation PFL non reussie');
        try {
          await page.waitForFunction(() => /\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+[A-Z]{3}\s+\d{1,2}\b/i.test(document.body.innerText), null, {timeout: 15000});
        } catch {}
        try {
          await page.waitForFunction(() => document.querySelectorAll('#fight_card_component .matchupRow a[href*="/fighter/"]').length >= 2, null, {timeout: 20000});
        } catch {}
        const snapshot = await page.evaluate(() => {
          const component = document.querySelector('#fight_card_component');
          const meta = document.querySelector('meta[property="og:title"]');
          const headings = [...document.querySelectorAll('h1, h2')]
            .map(element => (element.textContent || '').trim())
            .filter(text => text.length > 0);
          const title = (meta && meta.content) || headings[0] || '';
          const text = document.body.innerText;
          const dateMatch = text.match(/\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+[A-Z]{3}\s+\d{1,2}\b/i);
          const excerpt = dateMatch
            ? text.slice(Math.max(0, dateMatch.index - 80), dateMatch.index + 140)
            : text.slice(0, 200);
          const jsonld = [...document.querySelectorAll('script[type="application/ld+json"]')]
            .map(script => script.textContent || '');
          return {
            title: (title || '').trim(),
            text,
            html: component ? component.outerHTML : '',
            pageHtml: document.documentElement.outerHTML,
            rowCount: component ? component.querySelectorAll('.matchupRow').length : 0,
            dateFound: Boolean(dateMatch),
            excerpt,
            jsonld,
          };
        });
        candidate.title = snapshot.title;
        candidate.date_found = snapshot.dateFound;
        candidate.text_excerpt = snapshot.excerpt;
        candidate.row_count = snapshot.rowCount;
        candidate.card_html = redact(snapshot.html);
        candidate.page_html = redact(snapshot.pageHtml || '');
        const jsonldDate = extractJsonLdDate(snapshot.jsonld, url);
        if (jsonldDate) {
          candidate.jsonld_found = true;
          candidate.jsonld_start_date = jsonldDate;
          candidate.date = jsonldDate.slice(0, 10);
          candidate.start_at = jsonldDate;
          candidate.date_source = 'jsonld';
        }
        if (!candidate.date) {
          const extracted = extractDate(snapshot.text, url);
          if (extracted.date) {
            candidate.date = extracted.date;
            candidate.start_at = extracted.date;
            candidate.date_source = extracted.source;
          } else {
            candidate.date_source = extracted.source;
          }
        }
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
        console.log(JSON.stringify({
          source_url: candidate.source_url,
          title: candidate.title,
          date: candidate.date,
          date_found: candidate.date_found,
          date_source: candidate.date_source,
          text_excerpt: candidate.text_excerpt,
          jsonld_found: candidate.jsonld_found,
          jsonld_start_date: candidate.jsonld_start_date,
          row_count: candidate.row_count,
          extraction_status: candidate.extraction_status,
          error: candidate.error || null,
        }));
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