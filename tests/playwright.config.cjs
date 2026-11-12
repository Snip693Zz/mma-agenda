const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: 'agenda.spec.cjs',
  use: { browserName: 'chromium', viewport: { width: 390, height: 844 }, screenshot: 'only-on-failure' },
  webServer: { command: 'python3 -m http.server 8765 --bind 127.0.0.1', url: 'http://127.0.0.1:8765', reuseExistingServer: false }
});
