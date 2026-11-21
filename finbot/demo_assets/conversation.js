"use strict";
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => {
  const e = document.createElement(tag); if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls; return e;
};
const outcomes = {passed: "Passed every check", repaired: "Repaired, then passed", record_fallback: "Answered from the record by code",
  blocked: "Withheld", handled_by_code: "Handled by code"};
const reasonText = reason => ({status_mismatch: "states a status the record does not show",
  ungrounded_amount: "states an amount the record does not contain",
  value_from_other_record: "uses a value from a different record",
  record_identity_mismatch: "the lookup returned a different record than requested"}[reason.split(":")[0]] || reason);
function renderSteps(financial) {
  $("answer-steps").replaceChildren();
  if (!financial) return;
  const fetched = [...new Set(financial.evidence.filter(c => c.result && c.result.status === "found" && c.input && c.input.txn_id).map(c => c.input.txn_id))];
  $("answer-steps").append(node("li", `Fetched ${fetched.join(", ") || "no record"} again through the tool gateway; earlier answers are not reused.`));
  financial.steps.forEach(step => {
    const title = step.stage === "fallback" ? "Code built an answer from the record" : step.stage === "repair" ? "Model repair attempt" : "Model draft";
    const verdict = step.action === "allow" ? "passed the checks" : `rejected: ${step.reasons.map(reasonText).join("; ")}`;
    const item = node("li", undefined, step.action === "allow" ? "step-pass" : "step-block");
    item.append(node("strong", `${title}: `), node("span", verdict));
    if (step.action !== "allow") item.append(node("blockquote", step.answer));
    $("answer-steps").append(item);
  });
}
const labels = {kind: "Payment type", merchant: "Recipient", date: "Date", reference: "Reference", amount: "Amount", currency: "Currency"};
let scenarios = [], events = [], result = null, busy = false;
const scenario = () => scenarios.find(s => s.id === $("conversation-scenario").value);
function actionButton(label, event) {
  const button = node("button", label); button.type = "button";
  button.addEventListener("click", () => send([...events, event])); return button;
}
function render(data) {
  result = data;
  $("chat-messages").replaceChildren();
  if (!data.messages.length) $("chat-messages").append(node("p", "Send a message to begin. Finbot has not received your role-play notes or any payment details.", "hint"));
  data.messages.forEach(message => {
    const bubble = node("div", undefined, `chat-bubble ${message.role}${message.superseded ? " superseded" : ""}`);
    if (message.record_id) bubble.dataset.recordId = message.record_id;
    bubble.append(node("span", message.role === "user" ? "YOU" : message.superseded ? "FINBOT · EARLIER ANSWER, SUPERSEDED" : "FINBOT", "speaker"), node("span", message.text));
    $("chat-messages").append(bubble);
  });
  $("conversation-options").replaceChildren();
  if (data.pending) [...data.pending.options, "I'm not sure"].forEach(text => {
    $("conversation-options").append(actionButton(text, {type: "message", text}));
  });
  $("recognized-details").replaceChildren();
  if (!Object.keys(data.details).length && !data.unknown.length) $("recognized-details").append(node("p", "No identifying details received yet.", "hint"));
  Object.entries(data.details).forEach(([key, detail]) => {
    const row = node("div", undefined, "detail-row");
    row.append(node("strong", `${labels[key] || key}: ${detail.value}`),
      node("span", detail.certainty === "tentative" ? "Tentative — other possibilities remain" : "Supplied by you — used to find matching records", detail.certainty));
    $("recognized-details").append(row);
  });
  data.unknown.forEach(key => {
    const row = node("div", undefined, "detail-row");
    row.append(node("strong", `${labels[key] || key}: uncertain or unavailable`), node("span", "Finbot will not repeat this question in this conversation."));
    $("recognized-details").append(row);
  });
  const matches = data.candidates.filter(c => c.matches_supplied);
  $("selection-reason").textContent = !data.messages.length ? "Four authorized fictional records are available. Only what you send will narrow them." :
    data.selected_id ? `You confirmed ${data.selected_id}. The answer uses a fresh retrieval of that record.` :
    data.unresolved ? "No record selected. No financial answer released." :
    !matches.length ? "No records match all the explicit details. Check your message or leave unresolved." :
    data.pending ? `${matches.length} records match the explicit details. Asking about ${labels[data.pending.template].toLowerCase()} to reduce the remaining ambiguity.` :
    matches.length === 1 ? "One record matches the details you supplied. Confirm it to check its status." :
    "The remaining information does not identify one record. Choose only if you recognize it, or leave unresolved.";
  $("conversation-beliefs").replaceChildren();
  data.candidates.forEach(c => {
    const row = node("div", undefined, "belief-line");
    row.append(node("span", `${c.record_id} · ${c.kind} · ${c.merchant} · ${c.date} — ${(c.probability * 100).toFixed(1)}%`));
    const bar = node("progress"); bar.max = 1; bar.value = c.probability; bar.setAttribute("aria-label", c.record_id);
    row.append(bar); $("conversation-beliefs").append(row);
  });
  $("conversation-scores").replaceChildren(node("p", `${data.questions_asked}/2 questions asked. Scores consider records matching explicit details.`));
  data.ranking.forEach(q => $("conversation-scores").append(node("p", `${q.text} — wrong-record risk cut by ${(100 * q.error_reduction).toFixed(1)} points, value ${q.decision_value.toFixed(3)} after the question cost; ${q.information_gain_bits.toFixed(3)} bits expected gain`)));
  $("confirmation").hidden = !data.messages.length || Boolean(data.pending) || data.unresolved;
  $("leave-unresolved").hidden = !data.messages.length || data.unresolved;
  $("confirmation-title").textContent = data.selected_id ? "Change the selected record" : matches.length === 1 ? "Is this the payment?" : "Can you identify the payment?";
  $("matching-records").replaceChildren(); $("other-record-buttons").replaceChildren();
  data.candidates.forEach(c => {
    const button = actionButton(`${c.kind} · ${c.merchant} · ${c.date} · $200 · ${c.record_id}`, {type: "confirm", record_id: c.record_id});
    button.setAttribute("aria-pressed", String(c.record_id === data.selected_id));
    (c.matches_supplied ? $("matching-records") : $("other-record-buttons")).append(button);
  });
  $("other-records").hidden = matches.length === data.candidates.length;
  $("answer-check").hidden = !data.financial;
  $("answer-result").textContent = data.financial ? `${outcomes[data.financial.outcome] || data.financial.outcome}. ${data.financial.final.answer}` : "";
  renderSteps(data.financial);
  $("answer-evidence").textContent = data.financial ? JSON.stringify(data.financial, null, 2) : "";
  $("scenario-reference").hidden = !data.selected_id && !data.unresolved;
  $("reference-content").replaceChildren();
  $("reveal-reference").hidden = Boolean(data.reference);
  if (data.reference) $("reference-content").append(node("p", `Preset reference: ${data.reference.target_id || "No record in this catalogue"}`), node("p", data.reference.expected), node("p", data.reference.note));
  $("conversation-export").disabled = !events.length;
  $("conversation-status").textContent = data.messages.length ? "Conversation updated. You can add or correct details in your next message." : "Ready. Edit or send the starting message below.";
}
async function send(nextEvents, inspect = false) {
  if (busy || !scenario()) return;
  busy = true;
  const draft = $("customer-message").value;
  document.querySelectorAll("button, select, textarea").forEach(e => {e.disabled = true;});
  $("conversation-status").textContent = "Updating…";
  // A pending correction must never leave old financial evidence presented as current.
  $("answer-check").hidden = true; $("answer-evidence").textContent = ""; $("answer-steps").replaceChildren();
  document.querySelectorAll(".chat-bubble[data-record-id]").forEach(e => {
    e.classList.add("superseded"); e.querySelector(".speaker").textContent = "FINBOT · PREVIOUS ANSWER, UPDATE PENDING";
  });
  try {
    const response = await fetch("/api/conversation", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({scenario: scenario().id, events: nextEvents, inspect, fault: $("conversation-fault").value || "none"})});
    const data = await response.json();
    if (!response.ok) throw new Error("The conversation could not be updated. Keep messages under 500 characters and use at most 12 actions; start over for a longer conversation.");
    events = nextEvents; render(data);
    $("customer-message").value = "";
  } catch (error) {
    $("conversation-status").textContent = error.message;
    $("customer-message").value = draft;
  } finally {
    busy = false; document.querySelectorAll("button, select, textarea").forEach(e => {e.disabled = false;});
    $("conversation-export").disabled = !events.length;
  }
}
async function reset() {
  events = []; result = null;
  $("private-notes").open = false; $("belief-inspector").open = false;
  $("scenario-memory").textContent = scenario().memory;
  await send([]);
  $("customer-message").value = scenario().opening;
}
$("message-form").addEventListener("submit", e => {
  e.preventDefault(); const text = $("customer-message").value.trim();
  if (text) send([...events, {type: "message", text}]);
});
$("conversation-reset").addEventListener("click", reset);
$("conversation-scenario").addEventListener("change", reset);
$("conversation-fault").addEventListener("change", () => { if (events.length) send(events); });
$("leave-unresolved").addEventListener("click", () => send([...events, {type: "unresolved"}]));
$("reveal-reference").addEventListener("click", () => send(events, true));
$("conversation-export").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({...result, events}, null, 2)], {type: "application/json"}));
  const link = node("a"); link.href = url; link.download = "finbot-conversation-demo-v2.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try {
    const response = await fetch("/api/conversation/scenarios");
    if (!response.ok) throw new Error("Could not load conversation scenarios.");
    const catalogue = await response.json();
    scenarios = catalogue.scenarios;
    Object.entries(catalogue.faults || {none: "No injected fault"}).forEach(([key, title]) => {
      const option = node("option", title); option.value = key; $("conversation-fault").append(option);
    });
    scenarios.forEach(s => {const option = node("option", s.title); option.value = s.id; $("conversation-scenario").append(option);});
    await reset();
  } catch (error) {$("conversation-status").textContent = error.message;}
})();
