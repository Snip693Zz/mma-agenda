const { test, expect } = require('@playwright/test');
const base = 'http://127.0.0.1:8765';
for (const mode of ['absent', 'invalide', 'valide']) {
  test(`Affichage mobile et JSON ${mode}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    if (mode === 'absent') await page.route('**/mma-data.json', route => route.fulfill({ status: 404, body: 'Absent' }));
    if (mode === 'invalide') await page.route('**/mma-data.json', route => route.fulfill({ contentType: 'application/json', body: '{"events":[{}],"fighterRecords":{}}' }));
    await page.goto(base);
    await expect(page.locator('#calendar button[data-open]').first()).toBeVisible();
    await expect(page.locator('#nEvents')).toHaveText('8');
    await expect(page.locator('#nFights')).toHaveText('49');
    await expect(page.locator('#nFighters')).toHaveText('59');
    await expect(page.locator('#loadStatus')).toContainText(mode === 'valide' ? 'mma-data.json chargé' : 'intégrées conservées');
    await page.locator('#listBtn').click();
    await expect(page.locator('#listView')).toBeVisible();
    await expect(page.locator('#eventList [data-open]')).toHaveCount(8);
    await page.locator('#eventList [data-open]').first().click();
    await expect(page.locator('#eventDialog')).toBeVisible();
    await expect(page.locator('#eventBody')).toContainText('UFC 334');
    await expect(page.locator('#eventBody')).toContainText('Jared Gordon');
    await page.keyboard.press('Escape');
    await page.locator('#monthBtn').click();
    await page.locator('#next').click();
    await expect(page.locator('#monthTitle')).toContainText('décembre');
    await expect(page.locator('#calendar button[data-open]')).toHaveCount(4);
    expect(errors).toEqual([]);
  });
}
