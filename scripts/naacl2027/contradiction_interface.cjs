// Run with the local demo server, playwright and axe-core available to Node.
// FINBOT_DEMO_URL, CHROME_PATH, AXE_PATH and FINBOT_EVAL_OUT are optional overrides.
"use strict";
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {createHash} = require("node:crypto");
const base = process.env.FINBOT_DEMO_URL || "http://127.0.0.1:8765";
const root = path.resolve(__dirname, "../..");
const out = process.env.FINBOT_EVAL_OUT || path.join(root, "results/naacl2027");

(async () => {
  const axeSource = process.env.AXE_PATH ? await fs.readFile(process.env.AXE_PATH, "utf8") : require("axe-core").source;
  const browser = await chromium.launch(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {});
  const states = [], errors = [], externalRequests = [], checks = [];
  let axeVersion;
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({viewport: {width, height: 900}, bypassCSP: true});
      page.on("pageerror", e => errors.push(String(e)));
      page.on("request", r => {if (!r.url().startsWith(base + "/")) externalRequests.push(r.url());});
      const ready = () => page.waitForFunction(() => !busy && !document.querySelector("#message-send").disabled);
      const click = async locator => {await locator.click(); await ready();};
      const scan = async state => {
        await page.addScriptTag({content: axeSource});
        const scanned = await page.evaluate(async () => {
          const r = await axe.run(document, {runOnly: {type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"]}});
          return {version: axe.version, violations: r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length})),
            incomplete: r.incomplete.map(v => v.id)};
        });
        axeVersion = scanned.version;
        states.push({width, state, ...scanned});
        assert.deepEqual(scanned.violations, []);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      };
      await page.goto(base + "/study"); await ready();
      await page.selectOption("#conversation-scenario", "contradiction"); await ready();
      await click(page.locator("#message-send"));
      await page.locator("#other-records summary").click();
      await click(page.locator("#other-record-buttons button").filter({hasText: "txn_EMIX0001"}));
      assert.equal(await page.locator("#selection-conflict").isVisible(), true);
      assert.equal(await page.locator("#answer-check").isVisible(), false);
      assert.equal(await page.locator("#confirmation").isVisible(), false);
      assert.match(await page.locator("#conflict-details").innerText(), /you said Card payment; this record shows Bank transfer/);
      assert.equal(await page.evaluate(() => document.activeElement.id), "conflict-title");
      await scan("conflicting selection paused");
      if (process.env.FINBOT_SCREENSHOT_DIR) {
        await fs.mkdir(process.env.FINBOT_SCREENSHOT_DIR, {recursive: true});
        await page.locator("#selection-conflict").screenshot({path: path.join(process.env.FINBOT_SCREENSHOT_DIR, `conflict-${width}.png`)});
      }
      // Both controls are reachable from the focused explanation with the keyboard.
      await page.locator("#conflict-title").focus();
      await page.keyboard.press("Tab");
      assert.match(await page.evaluate(() => document.activeElement.textContent), /Use this record/);
      await page.keyboard.press("Tab");
      assert.match(await page.evaluate(() => document.activeElement.textContent), /Keep my earlier details/);
      await page.keyboard.press("Enter"); await ready();
      assert.equal(await page.locator("#selection-conflict").isVisible(), false);
      assert.match(await page.locator("#recognized-details").innerText(), /Payment type: Card payment/);
      assert.equal(await page.locator("#answer-check").isVisible(), false);
      await scan("kept details; confirmation still required");
      await click(page.locator("#matching-records button").filter({hasText: "txn_EMIX0002"}));
      assert.match(await page.locator("#answer-result").innerText(), /declined/);
      await click(page.locator("#other-record-buttons button").filter({hasText: "txn_EMIX0001"}));
      assert.equal(await page.locator("#answer-check").isVisible(), false);
      assert.equal(await page.locator(".chat-bubble[data-record-id]:not(.superseded)").count(), 0);
      await click(page.getByRole("button", {name: "Use this record and correct my details", exact: true}));
      assert.match(await page.locator("#recognized-details").innerText(), /Payment type: Bank transfer/);
      assert.match(await page.locator("#answer-result").innerText(), /txn_EMIX0001.*pending/);
      assert.equal(await page.locator("#selection-conflict").isVisible(), false);
      await scan("corrected details and confirmed alternative");
      await click(page.locator("#other-record-buttons button").filter({hasText: "txn_EMIX0002"}));
      await click(page.locator("#leave-unresolved"));
      assert.equal(await page.locator("#selection-conflict").isVisible(), false);
      assert.equal(await page.locator("#answer-check").isVisible(), false);
      await scan("left unresolved from conflict");
      checks.push({width, keyboard_resolution: true, retained_details: true, explicit_correction: true,
        no_current_answer_during_conflict: true, old_answer_superseded: true, unresolved_exit: true, no_horizontal_overflow: true});
      await page.close();
    }
    assert.deepEqual(errors, []); assert.deepEqual(externalRequests, []);
    const sources = {};
    for (const file of ["finbot/clarification_conversation.py", "finbot/demo_assets/conversation.js",
      "finbot/demo_assets/conversation.html", "finbot/demo_assets/conversation.css", "scripts/naacl2027/contradiction_interface.cjs"])
      sources[file] = createHash("sha256").update(await fs.readFile(path.join(root, file))).digest("hex");
    await fs.mkdir(out, {recursive: true});
    const report = {evaluation_type: "authored_browser_regression", page: "/study", browser: await browser.version(),
      standard: `WCAG 2.1 A and AA rules in axe-core ${axeVersion}`, sources, checks, states,
      violations: states.reduce((n, s) => n + s.violations.length, 0), browser_errors: errors, external_requests: externalRequests,
      limitations: ["Scripted browser checks, not a user study.", "Automatic accessibility scans do not establish full accessibility compliance."]};
    await fs.writeFile(path.join(out, "contradiction-interface.json"), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify({viewports: checks.length, axe_states: states.length, violations: report.violations, browser_errors: errors.length}));
  } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode = 1;});
