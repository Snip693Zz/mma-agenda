const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const DEFAULT_URL = 'https://www.pflmma.com/schedule/';
const OUT_DIR = path.join('artifacts', 'pfl');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function redact(text) {
  if (!text) return '';
  return String(text)
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[redacted-email]')
    .replace(/(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)/g, '[redacted-phone]');
}

async function main() {
  const url = process.env.PFL_SCHEDULE_URL || DEFAULT_URL;
  ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3000);
  const snapshot = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a[href]'));
    const candidates = links.map((a) => ({
      href: a.href,
      text: (a.textContent || '').trim(),
      heading: (a.closest('article,section,li,div')?.querySelector('h1,h2,h3')?.textContent || '').trim(),
      sectionText: (a.closest('article,section,li,div')?.textContent || '').slice(0, 500),
    }));
    return {
      title: document.title,
      bodyText: document.body.innerText.slice(0, 5000),
      links: candidates.filter((c) => c.href && c.text),
      pageHtml: document.documentElement.outerHTML,
    };
  });
  const report = {
    url,
    title: snapshot.title,
    body_text: redact(snapshot.bodyText),
    links: snapshot.links.map((l) => ({ ...l, text: redact(l.text), heading: redact(l.heading), section_text: redact(l.sectionText) })),
  };
  fs.writeFileSync(path.join(OUT_DIR, 'discovery-report.json'), JSON.stringify(report, null, 2));
  const eventLinks = snapshot.links.filter((l) => /event|fight|card/i.test(l.href) || /vs|championship|league/i.test(l.text));
  const candidates = eventLinks.map((l) => ({
    source_url: l.href,
    title: l.text || l.heading || '',
    heading: l.heading || '',
    section_text: l.sectionText || '',
    card_html: '',
    page_html: redact(snapshot.pageHtml),
  }));
  fs.writeFileSync(path.join(OUT_DIR, 'event-candidates.json'), JSON.stringify(candidates, null, 2));
  await browser.close();
}

main().catch((err) => { console.error(err); process.exit(1); });
