// Accessibility scan of the combined conversation demo (/study) in four states.
// Run from the repository root with the demo server on FINBOT_DEMO_URL (default port 18765):
//   node scripts/naacl2027/conversation_axe.cjs
"use strict";
const {chromium} = require("playwright");
const axe = require("axe-core");
const fs = require("node:fs/promises");
const path = require("node:path");

const base = process.env.FINBOT_DEMO_URL || "http://127.0.0.1:18765";
const out = process.env.FINBOT_EVAL_OUT || path.join(__dirname, "../../results/naacl2027");

async function scan(page, state) {
  await page.addScriptTag({content: axe.source});
  const result = await page.evaluate(async () => {
    const r = await window.axe.run(document, {runOnly: {type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"]}});
    return {violations: r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length})),
            incomplete: r.incomplete.map(v => v.id)};
  });
  return {state, ...result};
}

(async () => {
  const options = process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {};
  const browser = await chromium.launch(options);
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}, reducedMotion: "reduce", bypassCSP: true});
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto(`${base}/study`);
  await page.waitForFunction(() => !document.querySelector("#message-send").disabled);
  const states = [await scan(page, "start")];
  await page.selectOption("#conversation-fault", "amount_always");
  await page.click("#message-send");
  await page.waitForFunction(() => !document.querySelector("#message-send").disabled);
  states.push(await scan(page, "question asked"));
  for (let i = 0; i < 3 && await page.locator("#conversation-options button").count(); i++) {
    await page.click("#conversation-options button >> nth=0");
    await page.waitForFunction(() => !document.querySelector("#message-send").disabled);
  }
  states.push(await scan(page, "confirmation"));
  await page.locator("#matching-records button").first().click();
  await page.waitForSelector("#answer-steps li");
  await page.locator("#belief-inspector summary").click();
  states.push(await scan(page, "checked answer with rejected drafts"));
  await browser.close();
  const report = {page: "/study", standard: "WCAG 2.1 A and AA rules in axe-core " + axe.version, states,
                  violations: states.reduce((n, s) => n + s.violations.length, 0), browser_errors: errors};
  await fs.writeFile(path.join(out, "conversation-axe.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({states: states.length, violations: report.violations,
                              incomplete: [...new Set(states.flatMap(s => s.incomplete))], errors: errors.length}));
})();
