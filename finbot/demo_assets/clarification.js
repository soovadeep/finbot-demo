"use strict";
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (cls) item.className = cls;
  return item;
};
let events = [], result = null, active = null, busy = false;
const strategyLabels = {none: "No questions", fixed: "Fixed order", information_gain: "Information gain", decision_value: "Decision value"};
function button(label, event) {
  const item = node("button", label, "secondary"); item.type = "button";
  item.addEventListener("click", () => send([...events, event])); return item;
}
function render(data) {
  result = data;
  $("conversation").replaceChildren(node("p", data.case.question, "answer-text"));
  if (data.case.note) $("conversation").append(node("p", data.case.note, "hint"));
  data.trace.forEach(event => {
    if (event.event === "question") {
      const q = event.candidates.find(c => c.template === event.selected);
      $("conversation").append(node("p", `Finbot: ${q.text}`));
    } else if (event.event === "reply") $("conversation").append(node("p", `Customer: ${event.reply_category}`, "check-note"));
    else if (event.event === "confirm" || event.event === "correct") {
      $("conversation").append(node("p", `${event.event === "correct" ? "Corrected" : "Confirmed"} record: ${event.selected_id}`));
    } else $("conversation").append(node("p", "None of these records. No financial answer released."));
  });
  const top = [...data.candidates].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0];
  if (!data.pending && !data.selected_id && data.belief_source === "assumed_response_model" && top && top.probability > 0.5)
    $("conversation").append(node("p", `Finbot: My best guess is the ${top.kind.toLowerCase()} to ${top.merchant} on ${top.date} ` +
      `(${Math.round(100 * top.probability)}% likely). I won't act on a guess, so please confirm the record below.`));
  if (data.financial) $("conversation").append(node("p", `Finbot: ${data.financial.final.answer}`));
  $("reply-buttons").replaceChildren();
  if (data.pending) [...data.pending.options, "I'm not sure"].forEach(text => $("reply-buttons").append(
    button(text, {type: "reply", template: data.pending.template, text})));
  else if (data.belief_source === "catalogue_rejected") $("reply-buttons").append(node("p",
    "Conversation ended: the customer said none of these records is theirs, so Finbot gives no financial answer. " +
    "Start a new conversation to try again.", "hint"));
  else if (!data.selected_id) $("reply-buttons").append(node("p", data.questions_asked < data.question_budget ?
    "No question would narrow this down, so Finbot will not guess. Pick the exact record below, or choose none of them." :
    "The question budget is used up. Pick the exact record below, or choose none of them.", "hint"));
  // One path through the conversation: confirm a record, correct it at most once, or say none of them.
  // After "none of these" the conversation is over; nothing can be clicked again.
  const corrected = data.trace.some(e => e.event === "correct");
  $("record-buttons").replaceChildren();
  if (data.belief_source !== "catalogue_rejected") {
    if (!data.selected_id) data.candidates.forEach(c => $("record-buttons").append(button(
      `Confirm: ${c.record_id} · ${c.kind} · ${c.merchant} · ${c.date}`, {type: "confirm", record_id: c.record_id})));
    else if (!corrected) data.candidates.filter(c => c.record_id !== data.selected_id).forEach(c => $("record-buttons").append(button(
      `Wrong record? Use instead: ${c.record_id} · ${c.kind} · ${c.merchant} · ${c.date}`, {type: "confirm", record_id: c.record_id})));
    $("record-buttons").append(button(data.selected_id ? "Still wrong: none of these records" : "None of these records", {type: "none"}));
  }
  $("beliefs").replaceChildren(node("p", `Questions: ${data.questions_asked}/${data.question_budget} · Revision ${data.revision}`, "check-note"));
  data.candidates.forEach(c => {
    const label = data.belief_source === "user_selection" ? (c.record_id === data.selected_id ? "selected by customer" : "inactive") :
      data.belief_source === "catalogue_rejected" ? "catalogue rejected" : `${(100*c.probability).toFixed(1)}%`;
    $("beliefs").append(node("p", `${c.record_id}: ${label}`, "record-line"));
  });
  $("rankings").replaceChildren();
  const selection = [...data.trace].reverse().find(e => e.event === "question");
  if (selection) {
    $("rankings").append(node("p", "Scores when the most recent question was selected", "hint"));
    selection.candidates.forEach(q => {
      const detail = node("details");
      detail.append(node("summary", `${q.template === selection.selected ? "Selected · " : ""}${q.text}`),
        node("p", `${q.information_gain_bits.toFixed(3)} bits expected gain`, "record-line"),
        node("p", `Predicted error reduction: ${(100*q.error_reduction).toFixed(1)} percentage points; net decision value: ${q.decision_value.toFixed(3)}.`, "check-note"));
      $("rankings").append(detail);
    });
  } else $("rankings").append(node("p", "No clarification question selected.", "hint"));
  $("response-model").textContent = JSON.stringify(data.response_models, null, 2);
  $("dialogue-trace").textContent = JSON.stringify(data.trace, null, 2);
  $("clarify-answer").replaceChildren();
  if (data.financial) {
    $("clarify-answer").append(node("span", data.financial.outcome, "pill"), node("p", data.financial.final.answer, "answer-text"));
  } else $("clarify-answer").append(node("p", "No financial answer: the intended record is unresolved.", "empty"));
  $("financial-trace").textContent = data.financial ? JSON.stringify(data.financial, null, 2) : "No financial evidence fetched.";
  $("clarify-status").textContent = `${strategyLabels[data.strategy]} · ${data.status} · ${data.questions_asked} clarification question(s)`;
  $("clarify-download").disabled = false;
}
async function send(nextEvents, config = active) {
  if (busy || !config) return;
  busy = true;
  document.querySelectorAll("button, select").forEach(e => {e.disabled = true;});
  // Never present old financial evidence as current while a correction is pending.
  $("clarify-answer").replaceChildren(node("p", "Updating the current record…", "hint"));
  $("financial-trace").textContent = "";
  $("clarify-status").textContent = "Running clarification and verification…";
  try {
    const response = await fetch("/api/clarification", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...config, events: nextEvents})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Clarification failed.");
    events = nextEvents; active = config; render(data);
  } catch (error) {
    result = null;
    $("reply-buttons").replaceChildren(); $("record-buttons").replaceChildren();
    $("clarify-answer").replaceChildren(node("p", "No current answer. Start a new conversation.", "empty"));
    $("clarify-status").textContent = error.message;
  } finally {
    busy = false; document.querySelectorAll("button, select").forEach(e => {e.disabled = false;});
    $("clarify-download").disabled = !result;
  }
}
$("clarify-start").addEventListener("submit", event => {
  event.preventDefault();
  send([], {case_id: $("case").value, strategy: $("strategy").value, fault: $("clarify-fault").value});
});
$("clarify-download").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
  const link = node("a"); link.href = url; link.download = "finbot-clarification-trace.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
for (const id of ["case", "strategy", "clarify-fault"]) $(id).addEventListener("change", () => {
  if (result) $("clarify-status").textContent = "Settings changed. Start a new conversation to apply them; displayed results use the previous settings.";
});
(async () => {
  try {
    const response = await fetch("/api/clarification/cases");
    if (!response.ok) throw new Error("Could not load cases.");
    const config = await response.json();
    config.cases.forEach(c => {const option = node("option", c.title); option.value = c.id; $("case").append(option);});
    $("case").disabled = false; $("start").disabled = false;
    await send([], {case_id: "ambiguous", strategy: "information_gain", fault: "none"});
  } catch (error) {$("clarify-status").textContent = error.message;}
})();
