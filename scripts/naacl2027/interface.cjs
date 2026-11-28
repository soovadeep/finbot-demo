/* Automated engineering walkthrough, not a human usability study. */
"use strict";
const {chromium} = require("playwright");
const axe = require("axe-core");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const {execFileSync} = require("node:child_process");

const root = path.resolve(__dirname, "../..");
const base = process.env.FINBOT_DEMO_URL || "http://127.0.0.1:18765";
const parsed = new URL(base);
if (!["127.0.0.1", "localhost"].includes(parsed.hostname) || parsed.protocol !== "http:") {
  throw new Error("Use a loopback-only demo URL.");
}
const phase = process.env.FINBOT_EVAL_PHASE || "after";
if (!["before", "after"].includes(phase)) throw new Error("Phase must be before or after.");
const out = path.resolve(process.env.FINBOT_EVAL_OUT || path.join(root, "results/naacl2027"));
const checks = [], accessibility = [], errors = [], externalRequests = [];
const sha = (content) => crypto.createHash("sha256").update(content).digest("hex");

async function check(name, action) {
  try { await action(); checks.push({name, passed:true}); }
  catch (error) { checks.push({name, passed:false, error:error.message}); }
}

(async () => {
  await fs.mkdir(out, {recursive:true});
  const options = {headless:true};
  if (process.env.CHROME_PATH) options.executablePath = process.env.CHROME_PATH;
  const browser = await chromium.launch(options);
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1100}, reducedMotion:"reduce"});
    page.setDefaultTimeout(5000);
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== parsed.origin) {
        externalRequests.push(request.url());
      }
    });
    await page.goto(new URL("/inspector", base).href);
    await page.waitForFunction(() => !document.getElementById("run").disabled);
    async function inspect(id, fault) {
      await page.selectOption("#scenario", id);
      if (fault) await page.selectOption("#fault", fault);
      await page.click("#run");
      await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Inspection complete"));
    }
    async function axeCheck(state) {
      // Evaluation in the isolated automation context leaves the page CSP unchanged.
      await page.evaluate(axe.source);
      const result = await page.evaluate(async () => window.axe.run(document, {
        runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa","best-practice"]}
      }));
      accessibility.push({state, violations:result.violations.map(v => ({
        id:v.id,impact:v.impact,description:v.description,
        nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
        incomplete:result.incomplete.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
        passed_rules:result.passes.length});
    }
    const expected = {correct:"Draft passed checks",repair:"Repaired answer",fallback:"Built from the record",
      timeout:"Draft passed checks",pair:"Draft passed checks",binding:"Repaired answer",
      refusal:"Response withheld",policy:"Repaired answer"};
    await axeCheck("initial-desktop");
    for (const [id, outcome] of Object.entries(expected)) {
      await check(`preset-${id}`, async () => {
        await inspect(id);
        assert.equal(await page.locator("#answer .pill").textContent(),outcome);
        const downloadPromise=page.waitForEvent("download");
        await page.click("#download");
        const download=await downloadPromise;
        const trace=JSON.parse(await fs.readFile(await download.path(),"utf8"));
        assert.equal(trace.schema_version,2);
        assert.equal(trace.mode,"offline_scripted");
        assert.equal(trace.final.answer,await page.locator("#answer .answer-text").textContent());
      });
      await axeCheck(`${id}-desktop`);
    }
    await check("policy-source-and-keyboard-stage-selection",async()=>{
      await inspect("policy");
      assert.match(await page.locator("#draft").textContent(),/cards can be surcharged/);
      const repair=page.locator("#stages button").nth(1);
      await repair.focus(); await page.keyboard.press("Enter");
      assert.equal(await repair.getAttribute("aria-pressed"),"true");
      assert.equal(await page.locator('#stages [aria-pressed="true"]').count(),1);
      assert.match(await page.locator("#draft").textContent(),/cards cannot be surcharged/);
      assert.match(await page.locator("#draft blockquote").last().textContent(),/cards cannot be surcharged/);
    });
    await check("plain-language-binding-rejection",async()=>{
      await inspect("binding");
      assert.match(await page.locator("#draft").textContent(),/belongs to a different record/);
      assert.match(await page.locator("#draft code").first().textContent(),/value_from_other_record/);
    });
    await check("policy-mode-and-coverage-limits-visible",async()=>{
      await inspect("policy");
      assert.match(await page.locator("#policy-mode").textContent(),/complete supporting passage/);
      assert.match(await page.locator("#policy-mode").textContent(),/paraphrase/);
      assert.match(await page.locator("#policy-mode").textContent(),/applies to your case/);
    });
    await check("completed-question-remains-visible-after-edit",async()=>{
      await inspect("policy");
      await page.fill("#question","A different question");
      assert.match(await page.locator("#result-context").textContent(),/What are the surcharge rules/);
      assert.match(await page.locator("#status").textContent(),/previous run/);
      assert.equal(await page.locator("#download").isDisabled(),true);
    });
    await check("fallback-completeness-warning",async()=>{
      await inspect("pair","amount_always");
      assert.equal(await page.locator("#answer .pill").textContent(),"Built from the record");
      assert.match(await page.locator("#answer").textContent(),/may not cover every record/);
    });
    await check("busy-error-and-recovery",async()=>{
      const previous=await page.locator("#answer").textContent();
      let release;
      const gate=new Promise(resolve=>{release=resolve;});
      await page.route("**/api/run",async route=>{
        await gate;
        await route.fulfill({status:503,contentType:"application/json",body:'{"error":"Evaluation outage"}'});
      });
      try {
        await page.click("#run");
        assert.equal(await page.locator("#workspace").getAttribute("aria-busy"),"true");
        assert.equal(await page.locator("#run").isDisabled(),true);
        assert.equal(await page.locator("#download").isDisabled(),true);
        release();
        await page.waitForFunction(()=>document.getElementById("status").textContent.includes("Evaluation outage"));
        assert.equal(await page.locator("#answer").textContent(),previous);
        assert.match(await page.locator("#status").textContent(),/previous successful run/);
        assert.equal(await page.locator("#workspace").getAttribute("aria-busy"),"false");
        assert.equal(await page.locator("#run").isEnabled(),true);
      } finally { release(); await page.unroute("**/api/run"); }
      await inspect("correct");
      assert.equal(await page.locator("#download").isEnabled(),true);
    });
    await check("blank-input-does-not-submit",async()=>{
      let requests=0;
      const listener=req=>{if(req.url().endsWith("/api/run"))requests++;};
      page.on("request",listener);
      await page.fill("#question",""); await page.click("#run");
      assert.equal(await page.locator("#question").evaluate(el=>el.checkValidity()),false);
      assert.equal(requests,0); page.off("request",listener);
    });
    await inspect("policy");
    await page.locator("#stages button").nth(1).click();
    await page.locator("#evidence > details").first().evaluate(el=>{el.open=true;});
    await page.locator("#draft details").last().evaluate(el=>{el.open=true;});
    if(phase==="after") await page.screenshot({path:path.join(out,"interface-policy-desktop.png"),fullPage:true});
    await check("responsive-320-390-768-1440",async()=>{
      for(const width of [320,390,768,1440]) {
        await page.setViewportSize({width,height:844});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${width}px overflow`);
      }
    });
    await page.setViewportSize({width:390,height:844});
    await inspect("fallback");
    await page.locator("#stages button").last().click();
    await axeCheck("fallback-mobile");
    if(phase==="after") await page.screenshot({path:path.join(out,"interface-fallback-mobile.png"),fullPage:true});
    await check("accessibility-scan-no-violations",async()=>{
      assert.deepEqual(accessibility.flatMap(s=>s.violations.map(v=>`${s.state}:${v.id}`)),[]);
    });
    await check("no-javascript-errors-or-external-requests",async()=>{
      assert.deepEqual(errors,[]); assert.deepEqual(externalRequests,[]);
    });
    const sourceHashes={};
    for(const file of ["finbot/demo.py","finbot/demo_assets/index.html","finbot/demo_assets/app.js",
      "finbot/demo_assets/style.css","scripts/naacl2027/interface.cjs"]){
      sourceHashes[file]=sha(await fs.readFile(path.join(root,file)));
    }
    const report={created_utc:new Date().toISOString(),phase,mode:"automated_browser_engineering_evaluation",
      source_revision:execFileSync("git",["rev-parse","HEAD"],{cwd:root,encoding:"utf8"}).trim(),source_sha256:sourceHashes,
      browser:browser.version(),playwright:require("playwright/package.json").version,axe:axe.version,
      human_participants:0,limitations:["Not a usability study or proof of WCAG conformance.",
        "Axe incomplete checks need manual review; assistive-technology testing remains pending.",
        "Chromium only; no Safari, Firefox or real mobile-device evaluation."],
      checks,accessibility,errors,externalRequests,
      summary:{passed:checks.filter(c=>c.passed).length,total:checks.length,
        axe_states:accessibility.length,axe_violations:accessibility.reduce((n,s)=>n+s.violations.length,0)}};
    await fs.writeFile(path.join(out,`interface-${phase}.json`),JSON.stringify(report,null,2)+"\n");
    console.log(JSON.stringify(report.summary));
    for(const c of checks.filter(c=>!c.passed)) console.error(c.name,c.error);
    if(checks.some(c=>!c.passed)) process.exitCode=1;
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
