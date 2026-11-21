// Browser acceptance checks. Every exported action is explicitly rehearsal data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const base = process.env.FINBOT_DEMO_URL || 'http://127.0.0.1:8766';
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) throw new Error('Use a loopback URL.');
  const output = process.env.FINBOT_UI_OUTPUT;
  if (output) await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.FINBOT_CHROME ? {executablePath: process.env.FINBOT_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${base}/study/probes`);
    await page.waitForFunction(() => !document.getElementById('study-start').disabled);
    await page.selectOption('#study-mode', 'participant');
    assert.equal(await page.locator('#study-start').isDisabled(), true);
    await page.selectOption('#study-phase', 'development');
    assert.equal(await page.locator('#study-consent').evaluate(e => e.required), true);
    await page.locator('#study-start').click();
    assert.equal(await page.locator('#study-setup').isVisible(), true); // consent blocks submit
    await page.selectOption('#study-mode', 'rehearsal');
    await page.selectOption('#study-phase', 'evaluation');
    const act = async locator => {
      const response = page.waitForResponse(r => r.url() === `${base}/api/study` && r.request().method() === 'POST');
      await locator.click();
      const wire = await response; assert.equal(wire.status(), 200);
      const data = await wire.json();
      await page.waitForFunction(() => document.getElementById('study-status').textContent !== 'Updating…');
      if (!data.done) {
        assert.equal('export' in data, false);
        for (const field of ['probability', 'trace', 'expected', 'target_id', 'financial']) {
          assert.equal(JSON.stringify(data).includes(`"${field}"`), false);
        }
        assert.equal(await page.locator('#study-review').isVisible(), false);
      }
      return data;
    };
    const reply = name => act(page.getByRole('button', {name, exact: true}));
    const confirm = id => act(page.locator('#study-records button').filter({hasText: id}));
    const next = () => act(page.locator('#study-next'));
    await act(page.locator('#study-start'));
    assert.match(await page.locator('#study-question').textContent(), /type of payment/);
    if (output) await page.screenshot({path: path.join(output, 'study_participant.png')});
    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    if (output) await page.screenshot({path: path.join(output, 'study_mobile.png')});
    await page.setViewportSize({width: 1440, height: 1100});
    await reply('Bank transfer');
    assert.match(await page.locator('#study-question').textContent(), /date/);
    await reply('2026-11-15');
    await confirm('txn_EMIX0000'); // correction before saving
    await confirm('txn_EMIX0001');
    await next();
    await reply('2026-11-17'); await confirm('txn_EREP0001'); await next();
    for (let i = 0; i < 2; i++) await reply("I'm not sure");
    await reply('No matching record / I cannot distinguish them'); await next();
    assert.equal(await page.locator('#study-replies button').count(), 0);
    await reply('No matching record / I cannot distinguish them');
    const completed = await next();
    assert.deepEqual(completed.export.results.map(r => r.outcome),
      ['correct_selection', 'correct_selection', 'appropriate_unresolved', 'appropriate_unresolved']);
    const first = completed.export.results[0];
    assert.equal(first.corrections, 1);
    const updated = first.trace.filter(e => e.event === 'reply').at(-1).after;
    assert.ok(Math.abs(updated[1] - .765) < 1e-9);
    assert.equal(first.financial.outcome, 'passed');
    assert.match(first.financial.final.answer, /pending/);
    assert.doesNotMatch(JSON.stringify(first.financial), /txn_EMIX0000/);
    assert.match(await page.locator('#review-provenance').textContent(), /NOT HUMAN RESULTS/);
    const downloadExport = async filename => {
      const pending = page.waitForEvent('download'); await page.locator('#study-download').click();
      const download = await pending;
      const data = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
      assert.equal(data.request.mode, 'rehearsal');
      if (output) await fs.writeFile(path.join(output, filename), JSON.stringify(data, null, 2));
      return data;
    };
    await downloadExport('rehearsal_evaluation_assumed.json');
    if (output) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({path: path.join(output, 'study_researcher.png')});
    }
    await page.setViewportSize({width: 320, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.setViewportSize({width: 1440, height: 1100});
    await page.locator('#study-reset').click();
    await page.selectOption('#study-phase', 'development');
    await act(page.locator('#study-start'));
    for (const [answer, id] of [
      ['Card payment', 'txn_DKIND0000'], ['Bank transfer', 'txn_DKIND0001'],
      ['Atlas Market', 'txn_DMERCHANT0000'], ['Greenway', 'txn_DMERCHANT0001'],
      ['2026-11-12', 'txn_DDATE0000'], ['2026-11-13', 'txn_DDATE0001']
    ]) {
      await reply(answer); await confirm(id); await next();
    }
    const development = await downloadExport('rehearsal_development.json');
    assert.equal(development.results.length, 6);
    assert.deepEqual(errors, []);
    console.log('PASS: consent, evaluation lock, no premature label/probability disclosure, four evaluation tasks, six development probes, 76.5% posterior, correction evidence isolation, unresolved tasks, JSON exports, 320/390px layouts; no browser errors. All actions are rehearsal.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
