/* MMA Agenda V5 : lecture Supabase uniquement. Aucune clé secrète. */
'use strict';
if (!window.mmaSupabaseSync) window.mmaSupabaseSync = (async () => {
  const api = 'https://wxrxjwfktdviiasixupk.supabase.co/rest/v1/';
  const key = 'sb_publishable_QtGNjd9UKlZ70qa2MglLCQ_a38Gdip5';
  const statusEl = document.querySelector('#loadStatus');
  const controller = new AbortController();
  let timeout;
  function fallbackReady() {
    return new Promise((resolve, reject) => {
      const done = () => /mma-data\.json chargé|intégrées conservées/.test(statusEl.textContent);
      if (done()) return resolve();
      const observer = new MutationObserver(() => { if (done()) { clearTimeout(timer); observer.disconnect(); resolve(); } });
      const timer = setTimeout(() => { observer.disconnect(); reject(Error('Chargement de secours non terminé')); }, 7500);
      observer.observe(statusEl, { childList: true, characterData: true, subtree: true });
    });
  }
  async function rows(table, order) {
    const all = [];
    let total;
    for (let offset = 0; ; offset += 500) {
      const url = new URL(api + table);
      url.search = new URLSearchParams({ select: '*', order, offset: String(offset), limit: '500' });
      const response = await fetch(url, { method: 'GET', cache: 'no-store', signal: controller.signal, headers: { apikey: key, Prefer: 'count=exact' } });
      if (!response.ok) throw Error('Lecture Supabase refusée ou indisponible');
      const count = /\/(\d+)$/.exec(response.headers.get('content-range') || '');
      if (!count) throw Error('Comptage Supabase absent');
      const current = Number(count[1]);
      if (current > 50000 || (total !== undefined && total !== current)) throw Error('Volume trop grand ou données modifiées pendant la lecture');
      total = current;
      const page = await response.json();
      if (!Array.isArray(page) || page.length !== Math.min(500, Math.max(0, total - offset))) throw Error('Réponse Supabase incomplète');
      all.push(...page);
      if (all.length === total) return all;
    }
  }
  function safeUrl(value) {
    if (!value) return;
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol)) throw Error('Lien source invalide');
  }
  function snapshot(tables) {
    const [eventRows, cardRows, fightRows, fighterRows] = tables;
    if (!eventRows.length || !fighterRows.length) throw Error('Base vide ou inaccessible');
    const eventMap = new Map(), cardMap = new Map(), profiles = Object.create(null);
    for (const e of eventRows) {
      if (eventMap.has(e.id)) throw Error('Événement en double');
      [e.url, e.official_card_url, e.box_url].forEach(safeUrl);
      const value = { ...e.extra, id: e.id, org: e.org, title: e.title, date: e.event_date, place: e.place, official: e.official, url: e.url, note: e.note, cards: [] };
      if (e.official_card_url != null) value.officialCardUrl = e.official_card_url;
      if (e.box_url != null) value.boxUrl = e.box_url;
      if (e.verified != null) value.verified = e.verified;
      eventMap.set(e.id, value);
    }
    for (const c of cardRows) {
      const id = JSON.stringify([c.event_id, c.position]);
      if (!eventMap.has(c.event_id) || cardMap.has(id) || !Number.isInteger(c.position) || c.position < 0 || (c.start_at !== null && (typeof c.start_at !== 'string' || !Number.isFinite(Date.parse(c.start_at))))) throw Error('Carte incohérente');
      const value = { ...c.extra, name: c.name, start: c.start_at === null ? null : new Date(c.start_at).toISOString(), level: c.level, source: c.source, fights: [] };
      cardMap.set(id, value);
      eventMap.get(c.event_id).cards.push(value);
    }
    const fightIds = new Set();
    for (const f of fightRows) {
      const card = cardMap.get(JSON.stringify([f.event_id, f.card_position]));
      const id = JSON.stringify([f.event_id, f.card_position, f.position]);
      if (!card || fightIds.has(id) || !Number.isInteger(f.position) || f.position < 0 || !f.fighter_a || !f.fighter_b || f.fighter_a === f.fighter_b) throw Error('Combat incohérent');
      fightIds.add(id);
      card.fights.push([f.fighter_a, f.fighter_b]);
    }
    for (const f of fighterRows) {
      if (typeof f.name !== 'string' || !f.name || Object.hasOwn(profiles, f.name)) throw Error('Fiche incohérente');
      [f.url, f.nc_source, f.compare_url].forEach(safeUrl);
      const value = { ...f.extra, record: f.record, url: f.url, source: f.source, note: f.note };
      if (f.nc != null) { if (!Number.isInteger(f.nc) || f.nc < 0) throw Error('NC invalide'); value.nc = f.nc; }
      if (f.nc_source != null) value.ncSource = f.nc_source;
      if (f.compare_url != null) value.compare = f.compare_url;
      profiles[f.name] = value;
    }
    const initialOrder = new Map(data.map((e, i) => [e.id, i]));
    const events = [...eventMap.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)) || (initialOrder.get(a.id) ?? 1000000) - (initialOrder.get(b.id) ?? 1000000) || String(a.id).localeCompare(String(b.id)));
    const next = { events, fighterRecords: profiles };
    validate(next);
    return next;
  }
  try {
    await fallbackReady();
    timeout = setTimeout(() => controller.abort(), 12000);
    const next = snapshot(await Promise.all([
      rows('events', 'event_date.asc,id.asc'),
      rows('event_cards', 'event_id.asc,position.asc'),
      rows('fights', 'event_id.asc,card_position.asc,position.asc'),
      rows('fighters', 'name.asc')
    ]));
    const oldData = data, oldProfiles = fighterRecords;
    const org = document.querySelector('#org'), oldOptions = org.innerHTML, oldOrg = org.value;
    try {
      if (opened) { document.querySelector('#eventDialog').close(); opened = null; }
      data = next.events; fighterRecords = next.fighterRecords;
      org.innerHTML = '<option value="">Toutes les organisations</option>' + [...new Set(data.map(e => e.org))].map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
      org.value = [...org.options].some(o => o.value === oldOrg) ? oldOrg : '';
      render();
    } catch (error) {
      data = oldData; fighterRecords = oldProfiles; org.innerHTML = oldOptions; org.value = oldOrg; render(); throw error;
    }
    statusEl.textContent = 'Données : Supabase chargé en lecture seule';
    return { ok: true };
  } catch (error) {
    statusEl.textContent += ' · Supabase indisponible : données de secours conservées';
    return { ok: false, error: error.message };
  } finally { clearTimeout(timeout); controller.abort(); }
})();
