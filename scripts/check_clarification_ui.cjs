// Optional browser acceptance check. Requires Playwright and a running local demo.
// FINBOT_CHROME may select an installed Chrome executable.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const base = process.env.FINBOT_DEMO_URL || 'http://127.0.0.1:8766';
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) throw new Error('Use a local demo URL.');
  const output = process.env.FINBOT_UI_OUTPUT;
  if (output) await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(process.env.FINBOT_CHROME ? {executablePath: process.env.FINBOT_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${base}/clarification`);
    const settled = () => page.waitForFunction(() => !document.getElementById('start').disabled &&
      / · (clarifying|answered|unresolved|blocked) · /.test(document.getElementById('clarify-status').textContent));
    await settled();
    await page.getByRole('button', {name: 'Bank transfer', exact: true}).click(); await settled();
    assert.match(await page.locator('#beliefs').textContent(), /85\.7%/);
    await page.getByRole('button', {name: 'Greenway', exact: true}).click(); await settled();
    assert.match(await page.locator('#clarify-answer').textContent(), /No financial answer/);
    await page.getByRole('button', {name: /^Confirm: txn_BANK0002/}).click(); await settled();
    assert.match(await page.locator('#clarify-answer').textContent(), /pending/);
    assert.match(await page.locator('#beliefs').textContent(), /selected by customer/);
    assert.doesNotMatch(await page.locator('#beliefs').textContent(), /100\.0%/);
    await page.getByRole('button', {name: /^Wrong record\? Use instead: txn_CARD0001/}).click(); await settled();
    assert.match(await page.locator('#clarify-answer').textContent(), /declined/);
    assert.doesNotMatch(await page.locator('#financial-trace').textContent(), /txn_BANK0002/);
    assert.match(await page.locator('#dialogue-trace').textContent(), /invalidated_record/);
    assert.equal(await page.locator('#record-buttons button').count(), 1);  // one correction only
    await page.getByRole('button', {name: 'Still wrong: none of these records', exact: true}).click(); await settled();
    assert.equal(await page.locator('#financial-trace').textContent(), 'No financial evidence fetched.');
    assert.equal(await page.locator('#record-buttons button').count(), 0);  // the conversation is over
    assert.match(await page.locator('#reply-buttons').textContent(), /Conversation ended/);
    assert.match(await page.locator('#beliefs').textContent(), /catalogue rejected/);
    await page.locator('#start').click(); await settled();
    for (let n = 0; n < 2; n++) { await page.getByRole('button', {name: "I'm not sure", exact: true}).click(); await settled(); }
    assert.match(await page.locator('#clarify-status').textContent(), /unresolved/);
    assert.equal(await page.locator('#reply-buttons button').count(), 0);
    for (const scenario of ['explicit', 'premise', 'date', 'indistinguishable', 'uninformative']) {
      await page.selectOption('#case', scenario); await page.locator('#start').click(); await settled();
      if (scenario === 'premise') {
        assert.match(await page.locator('#clarify-answer').textContent(), /pending/);
        assert.doesNotMatch(await page.locator('#clarify-answer').textContent(), /declined|failure/);
      }
      if (['explicit', 'premise'].includes(scenario)) assert.match(await page.locator('#beliefs').textContent(), /Questions: 0\/2/);
    }
    await page.selectOption('#case', 'ambiguous'); await page.selectOption('#clarify-fault', 'amount_always');
    await page.locator('#start').click(); await settled();
    await page.getByRole('button', {name: /^Confirm: txn_BANK0002/}).click(); await settled();
    assert.match(await page.locator('#clarify-answer').textContent(), /record_fallback/);
    const downloaded = page.waitForEvent('download'); await page.locator('#clarify-download').click();
    const download = await downloaded;
    const trace = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
    assert.equal(trace.response_model_source, 'assumed_synthetic_not_calibrated');
    assert.deepEqual(trace.financial.steps.map(s => s.stage), ['draft', 'repair', 'fallback']);
    if (output) await page.screenshot({path: path.join(output, 'clarification-desktop.png'), fullPage: true});
    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    if (output) {
      await page.screenshot({path: path.join(output, 'clarification-mobile.png')});
      await page.locator('#clarify-answer').scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, 'clarification-mobile-answer.png')});
    }
    await page.goto(base); await page.waitForFunction(() => !document.getElementById('run').disabled);
    await page.selectOption('#scenario', 'repair'); await page.locator('#run').click();
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Inspection complete'));
    assert.match(await page.locator('#answer').textContent(), /Repaired answer/);
    assert.deepEqual(errors, []);
    console.log('PASS: posterior updates, explicit confirmation, correction evidence isolation, unresolved replies, six cases, real repair/fallback, trace export, 320/390px layout, original inspector; no browser errors.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
