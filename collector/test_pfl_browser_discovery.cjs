const test = require('node:test');
const assert = require('node:assert/strict');
const {allowed, isOfficialCardResponse, parseArgs, redact} = require('./pfl_browser_discovery.cjs');

test('official card endpoint is allowed with exact parameters', () => {
  assert.equal(allowed(
    'https://pflmma.com/ajax/get_fight_card_component',
    'POST',
    'event_tag=pfl-lyon-2026&is_mobile=0',
    'pfl-lyon-2026',
  ), true);
});

test('official card response matcher requires matching event tag', () => {
  assert.equal(isOfficialCardResponse(
    'https://pflmma.com/ajax/get_fight_card_component',
    'POST',
    'event_tag=pfl-lyon-2026&is_mobile=0',
    'pfl-lyon-2026',
  ), true);
  assert.equal(isOfficialCardResponse(
    'https://pflmma.com/ajax/get_fight_card_component',
    'POST',
    'event_tag=other-event&is_mobile=0',
    'pfl-lyon-2026',
  ), false);
});

test('csrf tokens are redacted', () => {
  const output = redact('const token = {"X-CSRF-TOKEN": "secret"};');
  assert.equal(output.includes('secret'), false);
  assert.equal(output.includes('[redacted]'), true);
});

test('defaults remain read-only discovery settings', () => {
  const args = parseArgs(['node', 'script']);
  assert.equal(args.listingUrl, 'https://pflmma.com/events');
  assert.equal(args.limit, 20);
});
