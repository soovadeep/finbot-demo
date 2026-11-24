/* Targeted local browser regression; no model calls or usability claims. */
"use strict";
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const root = path.resolve(__dirname, "../..");
const base = process.env.FINBOT_DEMO_URL || "http://127.0.0.1:18765/inspector";
const url = new URL(base);
if (url.protocol !== "http:" || !["localhost", "127.0.0.1"].includes(url.hostname)) throw Error("Use loopback HTTP.");
const out = process.env.FINBOT_EVAL_OUT || path.join(root, "results/naacl2027/financial-roles-interface.json");

(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {})});
  const errors = [], states = [], checks = [];
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 950}});
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(base);
    await page.waitForFunction(() => !document.getElementById("run").disabled);
    const axeSource = process.env.AXE_PATH ? await fs.readFile(process.env.AXE_PATH, "utf8") : require("axe-core").source;
    for (const width of [1280, 390]) {
      await page.setViewportSize({width, height: 950});
      for (const [id, field] of [["settlement_role", "settlement.actual_date"], ["refund_role", "refund.amount"]]) {
        await page.selectOption("#scenario", id);
        await page.click("#run");
        await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Inspection complete"));
        assert.equal(await page.locator("#answer .pill").textContent(), "Repaired answer");
        assert.match(await page.locator("#draft").textContent(), /financial_role_mismatch/);
        assert.ok((await page.locator("#draft").textContent()).includes(field));
        await page.locator("#draft details").evaluateAll(elements => elements.forEach(el => { el.open = true; }));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        const repair = page.locator("#stages button").nth(1);
        await repair.focus(); await page.keyboard.press("Enter");
        assert.equal(await repair.getAttribute("aria-pressed"), "true");
        assert.match(await page.locator("#draft").textContent(), /Refund amount: 50.00/);
        assert.match(await page.locator("#draft").textContent(), /Expected settlement date: 2026-11-20/);
        await page.evaluate(axeSource);
        const scan = await page.evaluate(() => window.axe.run(document, {runOnly: {type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"]}}));
        states.push({id, width, violations: scan.violations, incomplete: scan.incomplete.map(v => v.id)});
        assert.equal(scan.violations.length, 0);
        checks.push({id, width, passed: true});
      }
    }
    assert.deepEqual(errors, []);
    const files = ["finbot/demo.py", "finbot/demo_assets/app.js", "finbot/financial_roles.py", "scripts/naacl2027/financial_roles_interface.cjs"];
    const sources = {};
    for (const file of files) sources[file] = crypto.createHash("sha256").update(await fs.readFile(path.join(root, file))).digest("hex");
    await fs.writeFile(out, JSON.stringify({protocol: "finbot-role-interface-v1", browser: browser.version(), checks, states, errors, sources,
      limitations: ["Automated Chromium regression; no human usability or comprehension study.", "Axe is not proof of accessibility conformance."]}, null, 2) + "\n");
    console.log(`${checks.length}/${checks.length} role inspector states passed; no axe violations or JavaScript errors.`);
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
