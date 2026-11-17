const fs = require('node:fs/promises');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const HOSTS = new Set(['pflmma.com', 'www.pflmma.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'code.jquery.com', 'unpkg.com']);
function parseArgs(argv) {
  const args = {listingUrl: 'https://pflmma.com/events', output: 'reports/pfl-browser-discovery.json', limit: 20};
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--listing-url') args.listingUrl = argv[++i];
    else if (argv[i] === '--output') args.output = argv[++i];
    else if (argv[i] === '--limit') args.limit = Number(argv[++i]) || 20;
  }
  return args;
}
function allowed(value, method, body, tag) {
  try {
    const u = new URL(value);
    if (u.protocol !== 'https:' || u.username || u.password || u.port || !HOSTS.has(u.hostname)) return false;
    if (method === 'GET') return true;
    if (method !== 'POST' || u.origin !== 'https://pflmma.com' || u.pathname !== '/ajax/get_fight_card_component' || u.search) return false;
    const p = new URLSearchParams(body || '');
    return [...p].length === 2 && p.getAll('event_tag').length === 1 && p.getAll('is_mobile').length === 1 && p.get('event_tag') === tag && ['0', '1'].includes(p.get('is_mobile'));
  } catch { return false; }
}
function isOfficialCardResponse(url, method, body, tag) {
  return method === 'POST' && allowed(url, method, body, tag);
}
function redact(value) {
  return String(value).replace(/(['"])X-CSRF-TOKEN(['"])\s*:\s*(['"])[^'"]*/gi, '$1X-CSRF-TOKEN$2$3[redacted]');
}
function extractDate(text, eventUrl) {
  const m = text.match(/\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\b/i);
  if (!m) return {date: '', source: ''};
  const month = {JAN:1,FEB:2,MAR:3,APR:4,MAY:5,JUN:6,JUL:7,AUG:8,SEP:9,OCT:10,NOV:11,DEC:12}[m[2].toUpperCase()];
  if (!month) return {date:'', source:''};
  const suffix = `-${String(month).padStart(2,'0')}-${String(Number(m[3])).padStart(2,'0')}`;
  const year = String(eventUrl).match(/(?:^|[-\/])(20\d{2})(?:[-\/]|$)/);
  if (year) return {date: year[1] + suffix, source:'url_year'};
  const now = new Date();
  if (new Date(now.getFullYear(), month-1, Number(m[3])) >= new Date(now.getFullYear(), now.getMonth(), now.getDate())) return {date:now.getFullYear()+suffix, source:'visible_date+current_year_for_future'};
  return {date:'', source:'past_date_year_ambiguous'};
}
function extractJsonLdDate(payloads, eventUrl) {
  const expected = new URL(eventUrl).pathname.replace(/\/$/,'');
  for (const payload of payloads) {
    try {
      const stack = [JSON.parse(payload)];
      while (stack.length) {
        const item = stack.pop();
        if (!item || typeof item !== 'object') continue;
        if (Array.isArray(item)) { stack.push(...item); continue; }
        const types = Array.isArray(item['@type']) ? item['@type'] : [item['@type']];
        if (types.includes('Event') && item.startDate) {
          try { if (new URL(item.url).pathname.replace(/\/$/,'') === expected) return String(item.startDate); } catch {}
        }
        stack.push(...Object.values(item).filter(v => v && typeof v === 'object'));
      }
    } catch {}
  }
  return '';
}
async function main() {
  const args = parseArgs(process.argv);
  const {chromium} = require('@playwright/test');
  const browser = await chromium.launch({headless:true});
  const candidates = [];
  let eventLinks = [];
  async function contextFor(tag) {
    const context = await browser.newContext({serviceWorkers:'block', acceptDownloads:false});
    await context.route('**/*', route => {
      const r = route.request();
      return !allowed(r.url(),r.method(),r.postData(),tag) || ['image','media','font'].includes(r.resourceType()) ? route.abort() : route.continue();
    });
    return context;
  }
  try {
    const listing = await contextFor('');
    try {
      const page = await listing.newPage();
      const response = await page.goto(args.listingUrl,{waitUntil:'domcontentloaded',timeout:45000});
      if (!response || !response.ok()) throw Error('Navigation du calendrier PFL non reussie');
      eventLinks = await page.evaluate(() => [...new Set([...document.querySelectorAll('a[href]')].flatMap(a => {
        try { const u = new URL(a.href,location.origin); const m = u.pathname.match(/^\/event\/([A-Za-z0-9-]+)\/?$/); return u.hostname.replace(/^www\./,'') === 'pflmma.com' && m ? ['https://pflmma.com/event/'+m[1]] : []; } catch { return []; }
      }))]);
    } finally { await listing.close(); }
    for (const url of eventLinks.slice(0,args.limit)) {
      const tag = new URL(url).pathname.split('/').pop();
      const context = await contextFor(tag);
      const page = await context.newPage();
      const captures = [];
      page.on('response', response => {
        const request = response.request();
        if (isOfficialCardResponse(response.url(),request.method(),request.postData(),tag)) {
          captures.push(response.text().then(body => ({status:response.status(),body,content_type:response.headers()['content-type'] || ''})).catch(() => null));
        }
      });
      const c = {source_url:url,title:'',date:'',start_at:'',pairs:[],row_count:0,extraction_status:'not_available',date_found:false,date_source:'',text_excerpt:'',jsonld_found:false,jsonld_start_date:'',card_html:'',card_source:'',ajax_status:null,ajax_content_type:'',ajax_body_length:0,page_html:''};
      try {
        const response = await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
        if (!response || !response.ok()) throw Error('Navigation PFL non reussie');
        try { await page.waitForFunction(() => document.querySelectorAll('#fight_card_component .matchupRow a[href*="/fighter/"]').length >= 2,null,{timeout:20000}); } catch {}
        const s = await page.evaluate(() => {
          const component = document.querySelector('#fight_card_component');
          const text = document.body.innerText;
          const match = text.match(/\b(MON|TUE|WED|THU|FRI|SAT|SUN)\s+[A-Z]{3}\s+\d{1,2}\b/i);
          return {title:document.querySelector('meta[property="og:title"]')?.content || document.querySelector('h1,h2')?.textContent || '',text,html:component?.outerHTML || '',pageHtml:document.documentElement.outerHTML,rowCount:component?.querySelectorAll('.matchupRow').length || 0,dateFound:Boolean(match),excerpt:match ? text.slice(Math.max(0,match.index-80),match.index+140) : text.slice(0,200),jsonld:[...document.querySelectorAll('script[type="application/ld+json"]')].map(n => n.textContent || '')};
        });
        Object.assign(c,{title:s.title.trim(),date_found:s.dateFound,text_excerpt:s.excerpt,row_count:s.rowCount,page_html:redact(s.pageHtml)});
        const date = extractJsonLdDate(s.jsonld,url);
        if (date) Object.assign(c,{jsonld_found:true,jsonld_start_date:date,date:date.slice(0,10),start_at:date,date_source:'jsonld'});
        else { const d = extractDate(s.text,url); Object.assign(c,{date:d.date,start_at:d.date,date_source:d.source}); }
        const responses = (await Promise.all(captures)).filter(Boolean);
        const ajax = responses.find(r => r.status >= 200 && r.status < 300 && r.body.trim());
        c.card_html = redact(ajax ? ajax.body : s.html);
        c.card_source = ajax ? 'official_ajax_response' : 'rendered_component_fallback';
        if (ajax) Object.assign(c,{ajax_status:ajax.status,ajax_content_type:ajax.content_type,ajax_body_length:ajax.body.length});
        const extraction = spawnSync('python3',['-c','import sys,json; from collector.pfl_card_structure import extract_pairs; json.dump(extract_pairs(sys.stdin.read(), sys.argv[1], allow_fragment=(sys.argv[2] == "official_ajax_response")), sys.stdout)',url,c.card_source],{input:c.card_html,encoding:'utf8',maxBuffer:2000000});
        if (extraction.status !== 0) throw Error('Extraction Python non reussie: '+String(extraction.stderr).slice(0,300));
        const parsed = JSON.parse(extraction.stdout);
        Object.assign(c,{pairs:parsed.pairs || [],extraction_status:parsed.status,extraction_reason:parsed.reason,offending_row_index:parsed.offending_row_index,offending_row_links:parsed.offending_row_links || []});
      } catch (error) { c.error = redact(String(error)).slice(0,500); }
      finally { candidates.push(c); console.log(JSON.stringify({...c,card_html:undefined,page_html:undefined})); await context.close(); }
    }
  } finally { await browser.close(); }
  const report = {schema_version:2,mode:'pfl_browser_discovery',listing_url:args.listingUrl,generated_at:new Date().toISOString(),automatic_publication:false,database_writes:false,summary:{event_links:eventLinks.length,pages_fetched:candidates.length,metadata_found:candidates.filter(c => c.title && c.date).length,official_card_responses:candidates.filter(c => c.card_source === 'official_ajax_response').length},candidates};
  await fs.mkdir(path.dirname(args.output),{recursive:true});
  await fs.writeFile(args.output,JSON.stringify(report,null,2)+'\n','utf8');
  console.log(JSON.stringify(report.summary));
}
if (require.main === module) main().catch(error => { console.error(redact(String(error))); process.exitCode=1; });
module.exports = {allowed,isOfficialCardResponse,parseArgs,redact};
