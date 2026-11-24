"use strict";
const $ = (id) => document.getElementById(id);
const node = (tag, text, cls) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
};
const labels = { passed: "Draft passed checks", repaired: "Repaired answer", record_fallback: "Built from the record",
  blocked: "Response withheld", handled_by_code: "Handled by code" };
let scenarios = [];
let trace = null;

function chooseScenario() {
  const scenario = scenarios.find((s) => s.id === $("scenario").value);
  $("question").value = scenario.question;
  $("fault").value = scenario.fault;
  $("scenario-description").textContent = scenario.description;
  markEdited();
}

function markEdited() {
  if (trace) {
    $("status").textContent = "Inputs changed. Results below are from the previous run; run again to update.";
    $("result-context").classList.add("stale");
    $("download").disabled = true;
  }
}

function explainReason(reason) {
  const descriptions = {
    status_mismatch: "The draft's payment status disagrees with the retrieved record.",
    ungrounded_amount: "This amount is not supported by the eligible evidence.",
    value_from_other_record: "A claimed value belongs to a different record. Check each transaction's own fields.",
    currency_mismatch: "The currency does not match the named record's currency fields.",
    financial_role_mismatch: "The value is not supported by the field for this financial claim. An expected date is not an actual date; a payment amount is not a refund amount.",
    comparison_missing_record: "The answer omits one of the records you asked to compare.",
    comparison_missing_field: "A requested comparison field is missing or does not match that record.",
    comparison_missing_evidence: "One of the requested records has not been checked.",
    comparison_missing_unavailable_notice: "The answer must say which requested record could not be found.",
    comparison_unavailable_evidence: "A requested record could not be checked, so the comparison is incomplete.",
    comparison_claim_for_unavailable_record: "The answer states money details for a record that was not found.",
    policy_unsupported: "The policy statement has no complete supporting source sentence in its cited evidence.",
    policy_incomplete_context: "The quoted policy omits part of its supporting passage, such as a condition or exception.",
    policy_uncertain: "The policy reviewer could not establish support for this statement.",
    policy_empty_answer: "The draft contains no answer statement to verify.",
    policy_review_budget_exceeded: "The policy review exceeded its statement or size limit.",
    policy_reviewer_unavailable: "The policy reviewer was unavailable; the draft was withheld.",
    policy_review_invalid: "The policy review did not return complete, valid evidence for every statement."
  };
  return descriptions[reason.split(":")[0]] || "A configured verification rule rejected this claim. See the reason code below.";
}

function renderEvidence(calls, trustedCalls) {
  $("evidence").replaceChildren();
  if (!calls.length) $("evidence").append(node("p", "No tool evidence was retrieved for this stage.", "empty"));
  calls.forEach((call, index) => {
    const record = call.result.data;
    const card = node("details");
    const id = call.input.txn_id || call.input.query || "";
    card.append(node("summary", `${call.name} · ${call.result.status}`));
    card.append(node("p", id, "record-line"));
    if (record && !Array.isArray(record) && record.txn_id) {
      card.append(node("p", `${record.amount} ${record.currency} · ${record.status}`, "record-line"));
    }
    card.append(node("pre", JSON.stringify(call, null, 2)));
    if (trustedCalls && trustedCalls[index]) {
      const trusted = node("details");
      trusted.append(node("summary", "Evidence eligible for factual checks"),
        node("pre", JSON.stringify(trustedCalls[index], null, 2)));
      card.append(trusted);
    }
    $("evidence").append(card);
  });
}

function selectStage(index) {
  const step = trace.steps[index];
  [...$("stages").children].forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
  renderEvidence(step.evidence, step.trusted_evidence);
  $("evidence-caption").textContent = `Exact evidence checked against the ${step.stage} (${step.evidence.length} tool results).`;
  const draft = $("draft");
  draft.replaceChildren(node("span", step.action === "allow" ? "Passed implemented checks" : "Rejected by checks",
    `pill ${step.action === "block" ? "block" : ""}`));
  const injected = trace.injections.filter((item) => item.stage === step.stage);
  if (injected.length) draft.append(node("p", `Injected fault: ${injected.map((item) => item.marker).join("; ")}.`, "injected"));
  if (step.stage === "fallback") draft.append(node("p", "This candidate was constructed by code from the record and checked again.", "check-note"));
  draft.append(node("p", step.answer, "answer-text draft-text"));
  if (step.reasons.length) {
    const list = node("ul", undefined, "reason-list");
    step.reasons.forEach((reason) => {
      const item = node("li");
      item.append(node("p", explainReason(reason)), node("code", reason));
      list.append(item);
    });
    draft.append(list);
  } else {
    draft.append(node("p", "No violation was detected by the configured verifier chain.", "check-note"));
  }
  (step.checks || []).forEach((check) => {
    const detail = node("details");
    if (check.kind === "semantic_grounding") {
      detail.append(node("summary", `Bedrock evidence check: ${check.verdict}`),
        node("p", `Version ${check.version}; ${check.latency_ms} ms. A passing score is not proof of correctness or completeness.`, "check-note"));
      (check.filters || []).forEach((f) => detail.append(node("p",
        `${f.type}: score ${f.score}, threshold ${f.threshold}.`, "check-note")));
      if (check.verdict === "unavailable") detail.append(node("p",
        "The check could not complete. The answer was withheld; this is not a detected factual error.", "check-note"));
      draft.append(detail);
      return;
    }
    if (check.kind === "financial_role") {
      detail.append(node("summary", `${check.role.replaceAll("_", " ")}: ${check.verdict}`),
        node("p", check.text, "answer-text"),
        node("p", `Record: ${check.record_id || "unresolved"}. Field: ${check.path}. Claimed: ${check.claimed_value}. Recorded: ${check.evidence_value ?? "unavailable"}.`, "check-note"));
      draft.append(detail);
      return;
    }
    detail.append(node("summary", `Policy statement ${check.id + 1}: ${check.verdict} (${check.method})`),
      node("p", check.text, "answer-text"));
    check.evidence.forEach((evidence) => {
      detail.append(node("blockquote", evidence.quote));
      detail.append(node("p", evidence.source_url || evidence.source_id, "check-note"));
    });
    draft.append(detail);
  });
}

function render(result) {
  trace = result;
  $("stages").replaceChildren();
  result.steps.forEach((step, index) => {
    const title = step.stage === "fallback" ? "Record fallback" : step.stage === "repair" ? `Repair ${step.attempt}` : "Draft";
    const button = node("button", `${index + 1}. ${title} ${step.action === "allow" ? "✓" : "×"}`, "stage");
    button.type = "button";
    button.setAttribute("aria-label", `${title}: ${step.action === "allow" ? "passed implemented checks" : "rejected by checks"}`);
    button.setAttribute("aria-controls", "draft evidence");
    button.addEventListener("click", () => selectStage(index));
    $("stages").append(button);
  });
  if (result.steps.length) selectStage(0);
  else {
    renderEvidence(result.evidence);
    $("evidence-caption").textContent = "Tool results from this turn.";
    $("draft").replaceChildren(node("p", "The turn was handled before answer verification. No draft was checked.", "empty"));
  }
  $("answer").replaceChildren(node("span", labels[result.outcome], `pill ${result.final.blocked_by ? "block" : ""}`),
    node("p", result.final.answer, "answer-text"));
  if (result.final.blocked_by) $("answer").append(node("p", `Stopped by: ${result.final.blocked_by}`, "check-note"));
  if (result.outcome === "record_fallback") {
    $("answer").append(node("p", "This summary may not cover every record or every part of your question. Check it for completeness.", "coverage-note"));
  }
  if (result.outcome === "blocked" && result.steps.length && !result.steps.some((s) => s.stage === "fallback")) {
    $("answer").append(node("p", "No eligible record-built fallback was available.", "check-note"));
  }
  $("metrics").replaceChildren();
  const metrics = [["Local scripted latency", `${result.metrics.latency_ms} ms`], ["Scripted model calls", result.metrics.model_calls],
    ["Tool calls (including repair)", result.metrics.tool_calls], ["Injected faults applied", result.injections.length]];
  metrics.forEach(([name, value]) => $("metrics").append(node("dt", name), node("dd", value)));
  $("status").textContent = `Inspection complete · ${labels[result.outcome]} · ${result.injections.length} injected fault(s).`;
  $("result-context").textContent = `Displayed run: ${result.question} · Fault setting: ${result.fault}`;
  $("result-context").hidden = false;
  $("result-context").classList.remove("stale");
  $("download").disabled = false;
}

$("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  ["scenario", "question", "fault", "run"].forEach((id) => { $(id).disabled = true; });
  $("download").disabled = true;
  $("workspace").setAttribute("aria-busy", "true");
  $("status").textContent = "Running the scripted model through the verification pipeline…";
  try {
    const response = await fetch("/api/run", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: $("question").value, fault: $("fault").value})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Inspection failed.");
    render(result);
  } catch (error) {
    $("status").textContent = `${error.message} ${trace ? "Displayed results are from the previous successful run." : ""}`;
    if (trace) $("result-context").classList.add("stale");
  } finally {
    ["scenario", "question", "fault", "run"].forEach((id) => { $(id).disabled = false; });
    $("workspace").setAttribute("aria-busy", "false");
  }
});
$("download").addEventListener("click", () => {
  if (!trace) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(trace, null, 2)], {type: "application/json"}));
  const anchor = node("a");
  anchor.href = url;
  anchor.download = "finbot-offline-trace.json";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("scenario").addEventListener("change", chooseScenario);
$("question").addEventListener("input", markEdited);
$("fault").addEventListener("change", markEdited);

(async () => {
  try {
    const response = await fetch("/api/scenarios");
    if (!response.ok) throw new Error("Could not load scenarios. Reload the local demo.");
    const config = await response.json();
    scenarios = config.scenarios;
    scenarios.forEach((scenario) => {
      const option = node("option", scenario.title);
      option.value = scenario.id;
      $("scenario").append(option);
    });
    Object.entries(config.faults).forEach(([value, label]) => {
      const option = node("option", label);
      option.value = value;
      $("fault").append(option);
    });
    ["scenario", "fault", "run"].forEach((id) => { $(id).disabled = false; });
    chooseScenario();
    $("status").textContent = "Ready. Choose a scenario or enter your own question.";
  } catch (error) { $("status").textContent = error.message; }
})();
