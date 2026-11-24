"use strict";
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
};
let info, request = null, result = null, busy = false;
function choice(text, event, selected = false) {
  const button = node("button", text); button.type = "button";
  button.setAttribute("aria-pressed", String(selected));
  button.addEventListener("click", () => send({...request, events: [...request.events, event]}));
  return button;
}
function setupChanged() {
  const participant = $("study-mode").value === "participant";
  const evaluation = $("study-phase").value === "evaluation";
  $("study-consent").required = participant;
  $("study-start").textContent = participant ? "Start participant session →" : "Start rehearsal →";
  $("mode-label").textContent = participant ? "Participant pilot · fictional tasks" : "Rehearsal · not human study data";
  $("study-start").disabled = !info || busy || (participant && evaluation && !info.human_evaluation_ready);
  $("model-note").textContent = participant && evaluation && !info?.human_evaluation_ready ?
    "Participant evaluation is locked until the researcher loads a frozen participant development model." :
    evaluation ? ((participant ? info?.model_id : info?.rehearsal_model_id) ?
      "Evaluation uses the frozen server model." : "Rehearsal uses assumed probabilities.") :
    "Fixed probes collect replies for each question type. They do not test an adaptive selector.";
}
function beliefs(report, event) {
  const box = node("div", undefined, "belief-step");
  box.append(node("h4", `After “${event.reply_category}” · ${event.template} question`));
  report.candidates.forEach((candidate, i) => {
    const row = node("div", undefined, "belief-row");
    const bar = node("progress"); bar.max = 1; bar.value = event.after[i];
    bar.setAttribute("aria-label", `Belief for ${candidate.record_id}`);
    row.append(node("span", candidate.record_id), bar, node("span", `${(100 * event.after[i]).toFixed(1)}%`));
    box.append(row);
  });
  return box;
}
function review(data) {
  const exportData = data.export;
  $("review-provenance").textContent = `${data.mode === "rehearsal" ? "REHEARSAL — NOT HUMAN RESULTS" : "Participant pilot"} · ${data.phase} · ${exportData.strategy} · model ${exportData.model_id.slice(0, 16)}`;
  $("study-results").replaceChildren();
  exportData.results.forEach((report, i) => {
    const card = node("article", undefined, "result-card");
    card.append(node("h3", `Task ${i + 1} · ${report.outcome.replaceAll("_", " ")}`),
      node("p", `Expected: ${report.expected}`),
      node("p", `Observed: ${report.selected_id || "Left unresolved"}. ${report.question_count} question(s); ${report.corrections} correction(s).`));
    report.trace.filter(e => e.event === "reply").forEach(e => card.append(beliefs(report, e)));
    card.append(node("p", "Beliefs guide the next question. An explicit selection is still required before retrieving a financial answer.", "hint"));
    if (report.financial) {
      card.append(node("p", `Financial checks: ${report.financial.outcome} (separate from record-selection correctness).`, "record-line"),
        node("p", report.financial.final.answer, "answer-text"));
    } else card.append(node("p", "No record confirmed → no financial answer released.", "record-line"));
    const trace = node("details");
    trace.append(node("summary", "Question scores, belief updates, and financial trace"), node("pre", JSON.stringify(report, null, 2)));
    card.append(trace); $("study-results").append(card);
  });
}
function render(data) {
  result = data;
  $("study-setup").hidden = true; $("study-work").hidden = data.done; $("study-review").hidden = !data.done;
  $("study-status").textContent = data.done ? "Session complete. Download the export to retain it; nothing is saved by the server." :
    "Progress is kept in this page until completion. Refreshing discards it.";
  if (data.done) { review(data); return; }
  const task = data.current;
  $("study-progress").textContent = `Task ${data.completed_count + 1} of ${data.total}`;
  $("task-prompt").textContent = task.prompt;
  $("study-dialogue").replaceChildren();
  task.dialogue.forEach(turn => {
    const line = node("p"); line.append(node("strong", turn.question), node("span", `You: ${turn.reply}`));
    $("study-dialogue").append(line);
  });
  $("study-question").textContent = task.pending?.text || "";
  $("study-replies").replaceChildren();
  if (task.pending) [...task.pending.options, "I'm not sure"].forEach(text => {
    $("study-replies").append(choice(text, {type: "reply", template: task.pending.template, text}));
  });
  $("study-record-section").hidden = Boolean(task.pending);
  $("study-records").replaceChildren();
  if (!task.pending) {
    task.candidates.forEach(c => $("study-records").append(choice(
      `${c.kind} · ${c.merchant} · ${c.date} · ${c.record_id}`,
      {type: "confirm", record_id: c.record_id}, task.selected_id === c.record_id)));
    $("study-records").append(choice("No matching record / I cannot distinguish them", {type: "unresolved"}, task.unresolved));
  }
  $("study-selection").textContent = task.selected_id ? `Selected: ${task.selected_id}` : task.unresolved ? "This task will remain unresolved." : "No record selected yet.";
  $("study-next").disabled = !task.can_finish;
  $("study-next").textContent = data.completed_count + 1 === data.total ? "Finish session & see review →" : "Save task & continue →";
}
async function send(next) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button, select, input").forEach(e => {e.disabled = true;});
  $("study-status").textContent = "Updating…";
  try {
    const response = await fetch("/api/study", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(next)});
    const data = await response.json();
    if (!response.ok) throw new Error("Session request refused. Check consent, the assigned code, and the server’s frozen model. Your last accepted state is retained.");
    request = next; render(data);
  } catch (error) { $("study-status").textContent = error.message; }
  finally {
    busy = false;
    document.querySelectorAll("button, select, input").forEach(e => {e.disabled = false;});
    $("study-next").disabled = !result?.current?.can_finish;
    setupChanged();
  }
}
$("study-setup").addEventListener("submit", event => {
  event.preventDefault();
  send({protocol: info.protocol, participant_code: $("participant-code").value, mode: $("study-mode").value,
    phase: $("study-phase").value, consent: $("study-consent").checked, completed: [], events: []});
});
$("study-next").addEventListener("click", () => {
  if (!result?.current?.can_finish) return;
  send({...request, completed: [...request.completed, {task_id: result.current.task_id, events: request.events}], events: []});
});
$("study-download").addEventListener("click", () => {
  if (!result?.export) return;
  const blob = new Blob([JSON.stringify(result.export, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob), link = node("a"); link.href = url;
  link.download = `finbot-${request.mode}-${request.phase}-${request.participant_code}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("study-reset").addEventListener("click", () => {
  request = result = null; $("study-review").hidden = true; $("study-setup").hidden = false;
  $("study-results").replaceChildren(); $("study-consent").checked = false;
  $("study-status").textContent = "Ready for a new session. Assign a new code for each participant.";
  setupChanged();
});
for (const id of ["study-mode", "study-phase"]) $(id).addEventListener("change", setupChanged);
(async () => {
  try {
    const response = await fetch("/api/study");
    if (!response.ok) throw new Error("Could not load study configuration.");
    info = await response.json(); setupChanged();
    $("study-status").textContent = "Ready. Rehearsal is for trying the interface; its exports are not participant evidence.";
  } catch (error) { $("study-status").textContent = error.message; }
})();
