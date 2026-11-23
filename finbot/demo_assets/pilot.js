"use strict";
const $ = id => document.getElementById(id);
let catalogue, assignment, events = [], state, started, busy = false, finished = false;
const make = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
function button(label, event) {
  const b = make("button", label); b.type = "button";
  b.addEventListener("click", () => send(event)); return b;
}
function controls(disabled) {
  document.querySelectorAll("#session button, #session input, #session select").forEach(e => { e.disabled = disabled; });
}
function render() {
  const list = assignment.arm === "full_list";
  $("dialogue").replaceChildren();
  state.messages.filter(m => m.role === "user" || m.record_id || (!list && !state.unresolved))
    .forEach(m => $("dialogue").append(make("p", `${m.role === "user" ? "You" : "Finbot"}${m.superseded ? " (earlier answer, superseded)" : ""}: ${m.text}`)));
  $("options").replaceChildren();
  if (!list && state.pending) [...state.pending.options, "I'm not sure"].forEach(text =>
    $("options").append(button(text, {type: "message", text})));
  $("reply-form").hidden = list || state.unresolved;
  $("records").hidden = (!list && Boolean(state.pending)) || state.unresolved;
  $("matches").replaceChildren(); $("others").replaceChildren();
  state.candidates.forEach(c => {
    const b = button(`${c.kind} · ${c.merchant} · ${c.date} · ${c.amount} ${c.currency} · ${c.record_id}`,
      {type: "confirm", record_id: c.record_id});
    b.setAttribute("aria-pressed", String(c.record_id === state.selected_id));
    (list || c.matches_supplied ? $("matches") : $("others")).append(b);
  });
  $("other").hidden = list || !$("others").children.length;
  $("unresolved").hidden = state.unresolved;
  $("finish").hidden = !state.selected_id && !state.unresolved;
}
async function send(event) {
  if (busy || finished) return;
  if (events.length >= 12) { $("status").textContent = "The session event limit is reached. Stop and report this to the researcher."; return; }
  busy = true; controls(true);
  const next = [...events, {at_ms: Math.round(performance.now() - started), event}];
  try {
    const response = await fetch("/api/conversation", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({events: next.map(e => e.event), live: false, fault: "none"})});
    if (!response.ok) throw new Error("The session could not be updated. Retry or tell the researcher.");
    state = await response.json(); events = next; render();
    $("status").textContent = "Session updated.";
  } catch (e) { $("status").textContent = e.message; }
  finally { busy = false; controls(false); }
}
$("setup").addEventListener("submit", async e => {
  e.preventDefault();
  assignment = {participant_code: $("code").value, mode: $("mode").value, arm: $("arm").value,
    task: $("task").value, consent: $("consent").checked};
  if (!catalogue || !catalogue.tasks[assignment.task] || !catalogue.arms.includes(assignment.arm)) return;
  $("setup").hidden = true; $("session").hidden = false;
  $("memory").textContent = catalogue.tasks[assignment.task].memory;
  started = performance.now();
  await send({type: "message", text: catalogue.tasks[assignment.task].opening});
});
$("reply-form").addEventListener("submit", e => {
  e.preventDefault(); const text = $("reply").value.trim(); if (text) { send({type: "message", text}); $("reply").value = ""; }
});
$("unresolved").addEventListener("click", () => send({type: "unresolved"}));
$("finish").addEventListener("submit", e => {
  e.preventDefault(); if (busy || finished || !state || (!state.selected_id && !state.unresolved)) return;
  const report = {protocol: catalogue.protocol, ...assignment, events,
    elapsed_ms: Math.round(performance.now() - started), selected_id: state.selected_id, effort: Number($("effort").value)};
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], {type: "application/json"}));
  const a = document.createElement("a"); a.href = url; a.download = `finbot-pilot-${assignment.mode}-${assignment.participant_code}.json`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); finished = true; controls(true);
  $("status").textContent = "Session downloaded. Give this file to the researcher if you wish to include it.";
});
fetch("/api/pilot/tasks").then(async r => {
  if (!r.ok) throw new Error("Task instructions are unavailable.");
  catalogue = await r.json();
  const query = new URLSearchParams(location.search);
  for (const key of ["arm", "task"]) if ([...$(key).options].some(o => o.value === query.get(key))) $(key).value = query.get(key);
  if (/^P[0-9]{3,8}$/.test(query.get("participant") || "")) $("code").value = query.get("participant");
  $("start").disabled = false; $("status").textContent = "Ready. The researcher must assign the task and interface before you begin.";
}).catch(e => { $("status").textContent = e.message; });
