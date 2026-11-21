// Real browser acceptance of customer messages; no participant data or live models.
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
    await page.goto(`${base}/study`);
    await page.waitForFunction(() => !document.getElementById('message-send').disabled);
    assert.equal(await page.locator('#private-notes').evaluate(e => e.open), false);
    assert.equal(await page.locator('#reveal-reference').isVisible(), false);
    const act = async action => {
      const pending = page.waitForResponse(r => r.url() === `${base}/api/conversation` && r.request().method() === 'POST');
      await action(); const response = await pending; assert.equal(response.status(), 200);
      const data = await response.json();
      await page.waitForFunction(() => !document.getElementById('message-send').disabled);
      assert.equal(data.human_study_data, false);
      return data;
    };
    const send = async text => {
      if (text !== undefined) await page.locator('#customer-message').fill(text);
      return act(() => page.locator('#message-send').click());
    };
    const preset = id => act(() => page.selectOption('#conversation-scenario', id));
    const choose = text => act(() => page.getByRole('button', {name: text, exact: true}).click());
    const confirm = id => act(() => page.locator('#matching-records button').filter({hasText: id}).click());
    let result = await send();
    assert.equal(result.pending.template, 'kind');
    assert.equal('merchant' in result.details, false);
    assert.equal('reference' in result, false);
    if (output) await page.screenshot({path: path.join(output, 'conversation_vague.png')});
    result = await send('the little blue thing');
    assert.equal(result.pending.template, 'kind'); assert.equal(result.questions_asked, 1);
    result = await choose("I'm not sure"); assert.notEqual(result.pending.template, 'kind');
    result = await act(() => page.locator('#leave-unresolved').click());
    assert.equal(result.unresolved, true); assert.equal(result.financial, null);

    await preset('uncertain'); result = await send();
    assert.equal(result.pending.template, 'merchant');
    assert.equal(result.details.kind.certainty, 'tentative');
    assert.deepEqual(result.unknown, ['date']);
    assert.ok(result.candidates.every(c => c.probability > 0));
    await page.locator('#belief-inspector summary').click();
    if (output) await page.screenshot({path: path.join(output, 'conversation_uncertain.png')});
    result = await choose('Willow Repairs');
    assert.equal(result.candidates.filter(c => c.matches_supplied).length, 2);
    assert.equal(result.financial, null);

    await preset('complete'); result = await send();
    assert.equal(result.questions_asked, 0); assert.equal(result.pending, null);
    assert.equal(result.financial, null); assert.equal(result.details.merchant.value, 'Willow Repairs');
    assert.equal(await page.locator('#matching-records button').count(), 1);
    if (output) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({path: path.join(output, 'conversation_complete.png')});
    }
    result = await confirm('txn_EMIX0001'); assert.match(result.financial.final.answer, /pending/);
    result = await send('Actually, it was a card payment to Willow Repairs on November 16.');
    assert.equal(result.financial, null); assert.equal(result.selected_id, null);
    assert.equal(await page.locator('.chat-bubble.superseded').count(), 1);
    result = await confirm('txn_EMIX0002');
    assert.match(result.financial.final.answer, /declined/);
    assert.doesNotMatch(JSON.stringify(result.financial), /txn_EMIX0001/);
    await act(() => page.locator('#reveal-reference').click());
    assert.match(await page.locator('#reference-content').textContent(), /not a participant accuracy measurement/);
    const downloadPromise = page.waitForEvent('download'); await page.locator('#conversation-export').click();
    const download = await downloadPromise;
    const exported = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
    assert.equal(exported.protocol, 'finbot-conversation-demo-v2');
    assert.equal(exported.human_study_data, false);

    await preset('missing'); result = await send();
    assert.equal(result.candidates.filter(c => c.matches_supplied).length, 0);
    assert.equal(result.pending, null); assert.equal(result.financial, null);
    result = await act(() => page.locator('#leave-unresolved').click()); assert.equal(result.unresolved, true);
    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    if (output) await page.screenshot({path: path.join(output, 'conversation_mobile.png')});
    await page.goto(`${base}/study/probes`);
    await page.waitForFunction(() => !document.getElementById('study-start').disabled);
    assert.deepEqual(errors, []);
    console.log('PASS: customer message parsing, hidden private notes/reference, missing-detail questions, zero questions for complete input, tentative alternatives, unavailable date skipped, unknown/unsupported replies, corrections and evidence replacement, unmatched payment, demo-only export, mobile layout, legacy probe access; no browser errors.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
