"use strict";
/* HelpChoreAI page. Reads web/demo/ only, so it runs on any static host.
   On the local Python server it also enables sign-off and voice notes. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const NS = "http://www.w3.org/2000/svg";
const COLORS = { amber: "#F5A524", teal: "#2DD4BF", red: "#FF5A52", ink: "#F3F6F9", muted: "#93A1B2", line: "#263241", panel: "#121922", dev: "#4A94EE", sealed: "#DE5F98" };
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const D = { live: false };
const CURATED = ["P1_6w_8w", "P1_8w_10w", "P3_19w_26w"];

const pts = (x, d = 1) => (x >= 0 ? "+" : "−") + Math.abs(x * 100).toFixed(d);
const pct = (x) => Math.round(x * 100) + "%";
async function getJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json();
}
function svg(tag, attrs = {}, parent, text) {
  const e = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function el(tag, attrs = {}, parent, text) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (e.className = v) : e.setAttribute(k, v)));
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function canvas(host, w, h, label) {
  host.textContent = "";
  return svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": label }, host);
}
function tip(evt, text) {
  const t = $("#tip");
  if (!text) { t.hidden = true; return; }
  t.textContent = text; t.hidden = false;
  const x = Math.min(innerWidth - 250, evt.clientX + 12), y = Math.max(8, evt.clientY - 44);
  t.style.left = x + "px"; t.style.top = y + "px";
}
function hoverable(node, text) {
  const show = (e) => tip(e, text);
  node.addEventListener("pointerenter", show); node.addEventListener("pointermove", show);
  node.addEventListener("pointerleave", (e) => tip(e, null));
}
function drawPath(path, delay) {
  if (reduced) return;
  path.setAttribute("pathLength", 1);
  path.style.strokeDasharray = 1; path.style.strokeDashoffset = 1;
  path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: 600, delay, easing: "ease-out", fill: "forwards" });
}

/* ---------- Decision ---------- */
let heroDrawn = false;
function heroChart() {
  const host = $("#heroChart"), rows = D.visits.filter((v) => v.patient === "P3").sort((a, b) => a.week - b.week);
  const W = Math.max(300, host.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.5)));
  const m = { l: 40, r: 26, t: 30, b: 28 }, maxW = rows[rows.length - 1].week, maxY = 0.45;
  const X = (w) => m.l + ((W - m.l - m.r) * w) / maxW, Y = (v) => H - m.b - ((H - m.t - m.b) * v) / maxY;
  const s = canvas(host, W, H, "Line chart. One patient stays near 20 percent spiky cells for 19 weeks, reaches 38 percent at week 26 and returns to 20 percent at week 31.");
  [0, 0.1, 0.2, 0.3, 0.4].forEach((v) => {
    svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: COLORS.line }, s);
    svg("text", { x: m.l - 8, y: Y(v) + 4, "text-anchor": "end" }, s, pct(v));
  });
  const blocked = rows.filter((r) => r.blocked);
  const zoneL = X((rows[rows.length - 3].week + blocked[0].week) / 2);
  svg("rect", { x: zoneL, y: m.t - 12, width: W - m.r - zoneL + 12, height: H - m.b - m.t + 12, fill: COLORS.amber, opacity: 0.09 }, s);
  svg("text", { x: W - m.r + 6, y: H - m.b - 8, "text-anchor": "end", style: `fill:${COLORS.amber}` }, s, "failed quality check");
  const P = rows.map((r) => [X(r.week), Y(r.raw)]);
  const k = rows.length - 3;
  const line = (a, c, w) => svg("path", { d: "M" + a.map((p) => p.join(",")).join(" L"), fill: "none", stroke: c, "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" }, s);
  const p1 = line(P.slice(0, k + 1), COLORS.teal, 2.5), p2 = line(P.slice(k), COLORS.amber, 2.5);
  if (!heroDrawn) { drawPath(p1, 100); drawPath(p2, 650); heroDrawn = true; }
  rows.forEach((r, i) => {
    const peak = i === k + 1;
    svg("circle", { cx: P[i][0], cy: P[i][1], r: peak ? 7 : 4.5, fill: i > k ? COLORS.amber : COLORS.teal, stroke: COLORS.panel, "stroke-width": 2 }, s);
    const lab = W > 420 || [0, k, k + 1, k + 2].includes(i);
    if (lab) svg("text", { x: P[i][0], y: H - 8, "text-anchor": "middle" }, s, `${r.week}w`);
    hoverable(svg("circle", { cx: P[i][0], cy: P[i][1], r: 16, fill: "transparent" }, s),
      `Week ${r.week}: ${pct(r.raw)} spiky, ${pct(r.unreadable)} of cells unreadable`);
  });
  const big = (i, txt, dy, size, c) => { const t = svg("text", { x: P[i][0], y: P[i][1] + dy, "text-anchor": "middle" }, s, txt); t.style.fontSize = size + "px"; t.style.fill = c; t.style.fontWeight = 500; };
  big(k, pct(rows[k].raw), 24, 15, COLORS.ink);
  big(k + 1, pct(rows[k + 1].raw), -16, W > 480 ? 26 : 20, COLORS.amber);
  big(k + 2, pct(rows[k + 2].raw), 24, 15, COLORS.ink);
}

function alarmDots() {
  const host = $("#alarmDots"); host.textContent = "";
  const groups = [["confirmed", "confirmed: bigger than normal wobble"], ["ruled_out", "ruled out: inside normal wobble"],
    ["refused", "refused: recording not good enough"], ["missed", "missed by the normal reading"]];
  groups.forEach(([key, label]) => {
    const list = D.pairs.filter((p) => p.outcome === key), g = el("div", { class: "dotgroup" }, host), row = el("div", { class: "dotrow" }, g);
    list.forEach((p) => {
      const b = el("button", { class: `dot ${key}`, type: "button", "aria-pressed": "false", "aria-label": `${p.patient}, ${p.from} to ${p.to}`, "data-pair": p.id }, row);
      hoverable(b, `${p.patient} ${p.from} to ${p.to}: normal reading ${pts(p.raw)} points`);
      b.addEventListener("click", () => { setPair(p.id, "normal"); $("#explorer").scrollIntoView({ block: "start" }); });
    });
    const lab = el("p", { class: "grouplabel" }, g);
    el("b", {}, lab, (key === "missed" ? "+" : "") + list.length); lab.append(label);
  });
}

let cur = null, mode = "normal", shown = null;
function pairState(p, m) {
  if (m === "normal") return { pos: p.raw, band: p.naive_band, tone: p.naive_alarm ? "red" : "muted" };
  return { pos: p.adj, band: p.band, tone: p.decision === "exceeds_RCV" ? "teal" : p.decision === "indeterminate_QC" ? "amber" : "muted" };
}
function verdictText(p, m) {
  const f = `${p.from} to ${p.to}`;
  if (m === "normal") return p.naive_alarm ? `${f}: ${pts(p.raw)} points. Outside ±${(p.naive_band * 100).toFixed(1)}. Normal reading says alarm.`
    : `${f}: ${pts(p.raw)} points. Inside ±${(p.naive_band * 100).toFixed(1)}. Normal reading says nothing.`;
  if (p.decision === "indeterminate_QC") return `${f}: no decision. The recording failed the quality check.`;
  return p.decision === "exceeds_RCV" ? `${f}: ${pts(p.adj)} points. Bigger than the normal wobble of ±${(p.band * 100).toFixed(1)}.`
    : `${f}: ${pts(p.adj)} points. Inside the normal wobble of ±${(p.band * 100).toFixed(1)}. No change.`;
}
function bandChart(state, label) {
  const p = cur, host = $("#bandChart"), W = Math.max(300, host.clientWidth), H = 130;
  const span = Math.max(Math.abs(p.raw), Math.abs(p.adj), p.band, p.naive_band, 0.06) * 1.3;
  const X = (v) => W / 2 + ((W / 2 - 18) * v) / span;
  const s = canvas(host, W, H, label);
  const y0 = 50;
  svg("rect", { x: X(-state.band), y: y0 - 26, width: X(state.band) - X(-state.band), height: 52, rx: 4, fill: COLORS.line }, s);
  svg("text", { x: X(0), y: y0 + 44, "text-anchor": "middle" }, s, `normal wobble ±${(state.band * 100).toFixed(1)} points`);
  svg("line", { x1: 8, x2: W - 8, y1: y0, y2: y0, stroke: COLORS.muted, "stroke-width": 1 }, s);
  svg("line", { x1: X(0), x2: X(0), y1: y0 - 32, y2: y0 + 32, stroke: COLORS.muted }, s);
  svg("text", { x: X(0), y: y0 - 36, "text-anchor": "middle" }, s, "no change");
  const c = COLORS[state.tone];
  svg("line", { x1: X(0), x2: X(state.pos), y1: y0, y2: y0, stroke: c, "stroke-width": 3 }, s);
  svg("circle", { cx: X(state.pos), cy: y0, r: 9, fill: c, stroke: COLORS.bg || "#0B0F14", "stroke-width": 2 }, s);
  const t = svg("text", { x: Math.max(40, Math.min(W - 40, X(state.pos))), y: y0 + 26, "text-anchor": "middle" }, s, `${pts(state.pos)}`);
  t.style.fill = COLORS.ink; t.style.fontSize = "14px"; t.style.fontWeight = 500;
}
function animateBand(from, to, label) {
  if (reduced || !from) { bandChart(to, label); return; }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / 380), e = 1 - (1 - k) ** 3;
    bandChart({ pos: from.pos + (to.pos - from.pos) * e, band: from.band + (to.band - from.band) * e, tone: k > 0.5 ? to.tone : from.tone }, label);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function flowStrip() {
  const p = cur, rows = D.visits.filter((v) => v.patient === p.patient).sort((a, b) => a.week - b.week);
  const host = $("#flowStrip"), W = Math.max(300, host.clientWidth), H = 104, b = 22, t = 16;
  const maxF = Math.max(...rows.map((r) => r.flow));
  const s = canvas(host, W, H, `Bars of median flow at each visit for ${p.patient}.`);
  const step = (W - 8) / rows.length, bw = Math.min(26, step * 0.55);
  rows.forEach((r, i) => {
    const x = 4 + step * i + (step - bw) / 2, h = ((H - b - t) * r.flow) / maxF, on = r.visit === p.from || r.visit === p.to;
    svg("rect", { x, y: H - b - h, width: bw, height: h, rx: 3, fill: on ? COLORS.ink : COLORS.line }, s);
    if (step > 30 || on) svg("text", { x: x + bw / 2, y: H - 6, "text-anchor": "middle" }, s, r.visit);
    if (on) { const l = svg("text", { x: x + bw / 2, y: H - b - h - 5, "text-anchor": "middle" }, s, r.flow.toFixed(3)); l.style.fill = COLORS.ink; }
    hoverable(svg("rect", { x: 4 + step * i, y: 0, width: step, height: H, fill: "transparent" }, s), `Week ${r.week}: median flow ${r.flow.toFixed(3)} µL/s, ${r.runs} runs`);
  });
  $("#flowCaption").textContent = `How fast the cells moved at each visit, ${p.patient}. The two visits in this pair are bright.`;
}
function renderPair(animate) {
  const state = pairState(cur, mode);
  $("#modeNormal").setAttribute("aria-pressed", mode === "normal");
  $("#modeAdj").setAttribute("aria-pressed", mode === "adj");
  const label = verdictText(cur, mode);
  const v = $("#pairVerdict"); v.textContent = label; v.className = `reading ${state.tone === "muted" ? "" : state.tone}`;
  if (animate) animateBand(shown, state, label); else bandChart(state, label);
  shown = state;
  $$(".dot").forEach((d) => d.setAttribute("aria-pressed", d.dataset.pair === cur.id));
}
function setPair(id, m) {
  cur = D.pairs.find((p) => p.id === id); mode = m; shown = null;
  $("#pairSel").value = id;
  renderPair(false); flowStrip();
}
function decisionView() {
  const hl = D.headline.naive_binomial_vs_frozen, h = D.pairs.find((p) => p.id === "P3_19w_26w");
  $("#heroNaive").textContent = `${pts(h.raw)} points, alarm`;
  $("#heroAdj").textContent = `${pts(h.adj)} ±${(h.band * 100).toFixed(1)}`;
  $("#alarmsTitle").textContent = `A normal reading raises ${hl.alarms} alarms in ${hl.pairs_total} visit pairs`;
  const sel = $("#pairSel");
  ["P1", "P2", "P4", "P3", "P5"].forEach((pt) => {
    const g = el("optgroup", { label: `${pt}${pt === "P3" || pt === "P5" ? " (sealed)" : ""}` }, sel);
    D.pairs.filter((p) => p.patient === pt).forEach((p) => el("option", { value: p.id }, g, `${p.from} to ${p.to}`));
  });
  sel.addEventListener("change", () => setPair(sel.value, mode));
  $("#modeNormal").addEventListener("click", () => { mode = "normal"; renderPair(true); });
  $("#modeAdj").addEventListener("click", () => { mode = "adj"; renderPair(true); });
  $("#pairNext").addEventListener("click", () => {
    const i = CURATED.indexOf(cur.id); setPair(CURATED[(i + 1) % CURATED.length], "normal");
  });
  alarmDots(); heroChart(); setPair(CURATED[0], "normal");
  const t = D.tools;
  $("#heroFoot").textContent = `Built on SAM 3.1, Muse Spark 1.3, Muse Spark Open, Muse Voice Transcribe and Muse Code. Replay of signed results from public data (Reichel et al. 2022, CC BY 4.0). Live run: see README.`;
}

/* ---------- Cells ---------- */
let cell = null, cellGroup = "spiky", stepTimer = null;
function setStep(n) {
  $("#stage").dataset.step = n;
  $$("#view-cells .cellgrid [data-step]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.step) === String(n)));
}
function showCell(c, play) {
  cell = c;
  $("#cellImg").src = `demo/cells/${c.id}.png`;
  $("#cellImg").alt = `Microscope frame of one red blood cell, ${c.lab}, patient ${c.patient}, week ${c.visit}.`;
  $("#cellSvg").setAttribute("viewBox", `0 0 ${c.w} ${c.h}`);
  $("#polyStored").setAttribute("points", c.stored.map((p) => p.join(",")).join(" "));
  $("#polySam").setAttribute("points", c.sam.map((p) => p.join(",")).join(" "));
  $("#cellName").textContent = `${c.patient}, ${c.visit}, cell ${c.cell}`;
  $("#factDents").textContent = c.dents;
  $("#factSolid").textContent = Number(c.solidity).toFixed(3);
  $("#cellLabel").textContent = `The lab rated this cell ${c.lab}.` + (c.confidence ? ` SAM confidence ${c.confidence.toFixed(2)}.` : "");
  $$(".thumb").forEach((t) => t.setAttribute("aria-pressed", t.dataset.id === c.id));
  clearTimeout(stepTimer);
  if (play && !reduced) {
    setStep(0);
    stepTimer = setTimeout(() => { setStep(1); stepTimer = setTimeout(() => setStep(2), 1400); }, 700);
  } else setStep(2);
}
function gallery() {
  const host = $("#gallery"); host.textContent = "";
  D.cells.filter((c) => c.group === cellGroup).forEach((c) => {
    const b = el("button", { class: "thumb", type: "button", "data-id": c.id, "aria-pressed": cell && cell.id === c.id, "aria-label": `${c.patient} ${c.visit} cell ${c.cell}, rated ${c.lab}` }, host);
    el("img", { src: `demo/cells/${c.id}.png`, alt: "", loading: "lazy", width: 64, height: 48 }, b);
    b.addEventListener("click", () => showCell(c, true));
  });
  $$(".gallery-head [data-group]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.group === cellGroup));
}
function cellsView() {
  const s = D.headline.author_contour_solidity;
  $("#cellsLede").textContent = `Spikes are what the lab rates. But the tracking software saved a smooth outline for all ${s.n_cells.toLocaleString("en-US")} cells. SAM 3.1 follows the real edge.`;
  $("#cellLimit").textContent = "SAM measures shape. Added to our classifier it gave little gain on all cells and none on the sealed patients. In video mode it follows cells, but the difference between spiky and smooth disappears, so we measure on single frames.";
  $$("#view-cells .cellgrid [data-step]").forEach((b) => b.addEventListener("click", () => { clearTimeout(stepTimer); setStep(b.dataset.step); }));
  $$(".gallery-head [data-group]").forEach((b) => b.addEventListener("click", () => { cellGroup = b.dataset.group; gallery(); }));
  gallery();
  showCell(D.cells.find((c) => c.id === "P1-8w-122") || D.cells[0], false);
  setStep(0);
}

/* ---------- Signed report ---------- */
const TAMPER = {
  clinical: "\nAssessment: disease progression confirmed. We recommend treatment: start dasatinib.",
  paraphrase: "\nAssessment: The current therapy appears to be helping, so staying on the same dose makes sense.",
};
let rep = null, payloadText = "", lastTamper = null;
const word = { pass: "Pass", fail: "Fail", unsupported: "Cannot check" };
function gate(title, state, detail) {
  const li = el("li", { class: `gate ${state === "fail" ? "fail" : ""}` }, $("#gates"));
  const h = el("h4", {}, li, title); el("span", { class: state === "fail" ? "red" : state === "pass" ? "teal" : "" }, h, word[state] || state);
  return { li, detail };
}
async function runChecks() {
  const text = $("#reportText").value, g = $("#gates");
  const c = await HCAVerify.checkReport(rep, D.pin, payloadText, text);
  g.textContent = "";
  const sigState = [c.key, c.payload, c.report].includes("fail") ? "fail" : [c.key, c.payload, c.report].includes("unsupported") ? "unsupported" : "pass";
  const a = gate("1. Signature", sigState);
  const ul = el("ul", {}, a.li);
  [["Signed with the project key", c.key], ["Signed numbers unchanged", c.payload], ["Report text unchanged", c.report]].forEach(([k, v]) => {
    const li = el("li", {}, ul); el("span", {}, li, k); el("span", {}, li, word[v]);
  });
  const errs = c.parsed ? HCAVerify.localRules(text, c.parsed, D.rules) : ["Signed values could not be read"];
  const b = gate("2. Local rules", errs.length ? "fail" : "pass");
  if (errs.length) errs.slice(0, 4).forEach((e) => el("p", {}, b.li, e));
  else if (lastTamper === "paraphrase") el("p", {}, b.li, "No rule matched. Advice in normal words gets past fixed rules.");
  const edited = text !== rep.report || payloadText !== rep.payload_canonical;
  const au = rep.open_weight_audit;
  const bench = D.open.hosts.find((h) => h.version === "current") || D.open.hosts[0];
  const c3 = gate("3. Spark Open auditor", edited ? "stored" : au ? au.verdict : "not run");
  if (edited) {
    el("p", {}, c3.li, "This page calls no model, so edited text is not re-audited here.");
    if (lastTamper === "paraphrase" && bench) el("p", {}, c3.li, `Stored benchmark on ${bench.host}: Spark Open stopped ${bench.open.paraphrase12.hits} of 12 paraphrases. Local rules stopped ${bench.local.paraphrase12.hits} of 12.`);
  } else if (au) {
    el("p", {}, c3.li, `${au.model_id} on ${au.host || "baseten"}.`);
    (au.reasons || []).slice(0, 3).forEach((r) => el("p", {}, c3.li, r));
  } else el("p", {}, c3.li, "Waiting for the audit of this report.");
  const d = gate("4. Human sign-off", D.live ? "required" : "local only");
  if (D.live) signoffForm(d.li, edited || sigState !== "pass", c.parsed);
  else el("p", {}, d.li, "A researcher signs off in the local tool. This public page is read-only.");
  const v = $("#reportVerdict");
  if (sigState === "unsupported") { v.textContent = "This browser cannot verify Ed25519 signatures."; v.className = "reading amber"; return; }
  const said = { exceeds_RCV: "bigger than the normal wobble", within_RCV: "inside the normal wobble", indeterminate_QC: "no decision" };
  v.textContent = sigState === "pass" ? `Verified in your browser. Signed decision: ${said[c.parsed.decision]}.` : "Rejected. This does not match its signature.";
  v.className = `reading ${sigState === "pass" ? "teal" : "red"}`;
}
function signoffForm(li, blocked, parsed) {
  const f = el("div", { class: "signoff" }, li);
  const note = el("textarea", { rows: 2, placeholder: "Review note", "aria-label": "Review note" }, f);
  const row = el("div", { class: "row" }, f), out = el("p", {}, f);
  const send = async (decision) => {
    const [patient, from, to] = rep.id.split("_");
    const r = await (await fetch("/api/signoff", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient, from, to, decision, note: note.value.trim(), payload_sha256: parsed.payload_sha256, report_sha256: parsed.report_sha256 }) })).json();
    out.textContent = r.error ? `Sign-off refused: ${r.error}` : `${decision}. Bound to ${parsed.payload_sha256.slice(0, 12)}.`;
  };
  ["Approve", "Flag"].forEach((d) => { const b = el("button", { class: "ghost", type: "button" }, row, d); b.disabled = blocked; b.addEventListener("click", () => send(d)); });
  dictateButton(row, note, out);
}
async function loadReport(id) {
  rep = await getJSON(`demo/reports/${id}.json`);
  payloadText = rep.payload_canonical; lastTamper = null;
  $("#reportText").value = rep.report;
  const trail = $("#agentTrail"); trail.textContent = "";
  const a = rep.agent;
  if (a && a.tools && a.tools.length) {
    a.tools.forEach((t) => el("li", {}, trail, t));
    $("#agentNote").textContent = `Status: ${a.status}. Tool calls: ${a.tools.length}. Refusals: ${a.refusals}. The model chose this order; the checks live inside the tools.`;
  } else $("#agentNote").textContent = `Status: ${a ? a.status : "not recorded"}.`;
  await runChecks();
}
function tamper(kind) {
  const p = JSON.parse(rep.payload_canonical), box = $("#reportText");
  lastTamper = kind === "reset" ? null : kind;
  box.value = rep.report; payloadText = rep.payload_canonical;
  if (kind === "number") box.value = rep.report.replace(`${p.delta_adj >= 0 ? "+" : ""}${p.delta_adj.toFixed(4)}`, "+0.9999");
  if (TAMPER[kind]) box.value = rep.report + TAMPER[kind];
  if (kind === "byte") payloadText = rep.payload_canonical.replace(/("delta_adj":-?0\.)(\d)/, (m, a, d) => a + ((Number(d) + 1) % 10));
  runChecks();
}
function reportView() {
  const sel = $("#reportSel");
  D.reportIndex.forEach((id) => el("option", { value: id }, sel, id.replaceAll("_", " ")));
  sel.addEventListener("change", () => loadReport(sel.value));
  $$("[data-tamper]").forEach((b) => b.addEventListener("click", () => tamper(b.dataset.tamper)));
  let t; $("#reportText").addEventListener("input", () => { clearTimeout(t); t = setTimeout(runChecks, 200); });
  sel.value = "P1_6w_8w"; return loadReport(sel.value);
}

/* ---------- Method ---------- */
function flowChart() {
  const host = $("#flowChart"), W = Math.max(300, host.clientWidth), H = Math.round(Math.min(340, Math.max(240, W * 0.42)));
  const m = { l: 44, r: 16, t: 14, b: 40 }, pts_ = D.flow.points;
  const xs = pts_.map((p) => Math.log(p[1])), lo = Math.min(...xs), hi = Math.max(...xs);
  const X = (f) => m.l + ((W - m.l - m.r) * (Math.log(f) - lo)) / (hi - lo), Y = (v) => H - m.b - (H - m.t - m.b) * v;
  const s = canvas(host, W, H, "Scatter of runs. The share of spiky cells falls as flow rises, with the same slope in development and sealed patients.");
  [0, 0.5, 1].forEach((v) => { svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: COLORS.line }, s); svg("text", { x: m.l - 8, y: Y(v) + 4, "text-anchor": "end" }, s, pct(v)); });
  [0.002, 0.005, 0.01, 0.02].forEach((f) => { if (Math.log(f) >= lo && Math.log(f) <= hi) svg("text", { x: X(f), y: H - m.b + 16, "text-anchor": "middle" }, s, f); });
  svg("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle" }, s, "flow, µL/s (log scale)");
  pts_.forEach((p) => {
    const x = X(p[1]), y = Y(p[2]), c = p[0] === "dev" ? COLORS.dev : COLORS.sealed;
    if (p[0] === "dev") svg("circle", { cx: x, cy: y, r: 2.4, fill: c, opacity: 0.5 }, s);
    else svg("rect", { x: x - 2.2, y: y - 2.2, width: 4.4, height: 4.4, fill: c, opacity: 0.6, transform: `rotate(45 ${x} ${y})` }, s);
  });
  [["dev", "dev"], ["sealed", "sealed"]].forEach(([k, name]) => {
    const f = D.flow.fits[k], c = COLORS[k];
    svg("path", { d: "M" + f.curve.map((q) => `${X(q[0])},${Y(q[1])}`).join(" L"), fill: "none", stroke: COLORS.panel, "stroke-width": 5 }, s);
    svg("path", { d: "M" + f.curve.map((q) => `${X(q[0])},${Y(q[1])}`).join(" L"), fill: "none", stroke: c, "stroke-width": 2 }, s);
  });
  const lg = el("p", { class: "tiny" }, null, "");
  lg.textContent = `● development patients, slope ${D.flow.fits.dev.slope.toFixed(2)}   ◆ sealed patients, slope ${D.flow.fits.sealed.slope.toFixed(2)}`;
  host.appendChild(lg);
}
function planner() {
  const target = +$("#plTarget").value / 100, p = +$("#plP").value / 100, phi = +$("#plPhi").value, cells = +$("#plCells").value;
  if (!(target > 0 && p > 0 && p < 1 && phi > 0 && cells > 0)) { $("#planOut").textContent = "Enter positive numbers."; return; }
  const perCell = phi * p * (1 - p), need = (target / 1.96) ** 2 / 2, runs = Math.ceil(perCell / need / cells);
  $("#planOut").textContent = `${runs} runs per visit, ${(runs * cells).toLocaleString("en-US")} cells.`;
}
function methodView() {
  const host = $("#predictions");
  D.predictions.forEach((p) => {
    const r = el("div", { class: "pred" }, host);
    el("div", {}, r, p.said); el("div", { class: "found" }, r, p.found);
    el("div", { class: `res ${p.result === "Held" ? "teal" : "amber"}` }, r, p.result);
  });
  [`SAM shape added little to the classifier: agreement 0.24 to 0.28 on all cells, and none on sealed patients.`,
    `AI raters agreed only weakly with the human on 100 random cells (AC1 0.35 for Spark, 0.25 for Spark Open).`,
    `Muse Spark Open as a cell reader. It read all ${D.open.reader.cells_read.toLocaleString("en-US")} cells, but its visit share did not follow the human one (correlation ${D.open.reader.within_patient_spearman.toFixed(2)}, error ${Math.round(D.open.reader.calibrated_mae_points)} points). By a rule frozen before the run, it does not read cells here.`,
    `One of five predictions held fully.`].forEach((t) => el("li", {}, $("#notWorked"), t));
  const cl = D.open.claims, said = { exceeds_RCV: "bigger than wobble", within_RCV: "inside wobble", indeterminate_QC: "no decision" };
  $("#claimNote").textContent = `A study can overstate a result without changing a number. Muse Spark Open stopped ${cl.spark_open_stopped} of ${cl.beyond_data} sentences that said more than the signed result and passed ${cl.spark_open_passed_fair} of ${cl.fair} fair ones. A fixed word list stopped ${cl.word_list_stopped}. On a harder set it stopped ${cl.hard.spark_open_stopped} of ${cl.hard.beyond_data} and passed ${cl.hard.spark_open_passed_fair} of ${cl.hard.fair}; the word list stopped ${cl.hard.word_list_stopped}. We wrote these sentences ourselves, so this is a first test.`;
  const ct = $("#claimTable"), ch = el("tr", {}, el("thead", {}, ct));
  ["Sentence", "Signed result", "Right answer", "Word list", "Spark Open"].forEach((h) => el("th", { scope: "col" }, ch, h));
  const cb = el("tbody", {}, ct);
  D.open.claims_hard.forEach((c) => {
    const r = el("tr", {}, cb);
    [c.sentence, said[c.decision], c.want, c.word_list, c.spark_open].forEach((x) => el("td", {}, r, x));
  });
  const par = D.open.parity.filter((r) => r.equal === true || r.equal === "True");
  $("#parityNote").textContent = D.open.parity.length
    ? `${par.length} of ${D.open.parity.length} reports signed by the open model have the same numbers as the cloud run. The numbers come from code, so the model can be swapped.`
    : "Results will appear here after the open-weight runs.";
  const t = $("#hostTable"), head = el("tr", {}, el("thead", {}, t));
  ["Host", "Prompt", "Paraphrased advice stopped", "Tampered reports stopped", "Clean reports passed"].forEach((h) => el("th", { scope: "col" }, head, h));
  const body = el("tbody", {}, t);
  D.open.hosts.forEach((h) => {
    const r = el("tr", {}, body);
    [h.host, h.version, `${h.open.paraphrase12.hits} of 12`, `${h.open.tampered12.hits} of 12`, `${h.open.clean12.hits} of 12`].forEach((x) => el("td", {}, r, x));
    const l = el("tr", {}, body);
    ["local rules", h.version, `${h.local.paraphrase12.hits} of 12`, `${h.local.tampered12.hits} of 12`, `${h.local.clean12.hits} of 12`].forEach((x) => el("td", {}, l, x));
  });
  [`Five patients, one lab, one human rater.`, `The false-alarm simulation splits runs within one visit. It does not cover day-to-day variation.`,
    `With this protocol, changes under about ${(D.headline.rcv95.median * 100).toFixed(0)} points cannot be called. Power is 31% at 5 points and 77% at 10 points.`,
    `The lab's label pools two kinds of spiky cell.`, `Why speed changes the reading is not measured here. Only that it does.`,
    `This does not diagnose or treat. Whether red cell shape tracks the disease in the brain is unknown.`].forEach((x) => el("li", {}, $("#limits"), x));
  const ex = D.example;
  $("#exampleNote").textContent = `Example with made-up data and a known answer: a real rise at S1 visit 3, a false alarm at S2 visit 3 from samples that waited too long, a bad recording at S2 visit 4. The tool recovered the disturbance slope (${ex.info.slope.toFixed(2)}, planted -0.32).`;
  const et = $("#exampleTable"), eh = el("tr", {}, el("thead", {}, et));
  ["Pair (synthetic)", "Normal reading", "Corrected", "Wobble", "Decision"].forEach((h) => el("th", { scope: "col" }, eh, h));
  const eb = el("tbody", {}, et);
  ex.pairs.forEach((p) => {
    const r = el("tr", {}, eb);
    [`${p.subject} ${p.from} to ${p.to}`, `${pts(p.normal_change)} ${p.normal_says}`, pts(p.corrected_change), (p.wobble * 100).toFixed(1), p.meaning].forEach((x) => el("td", {}, r, x));
  });
  const pt = $("#pairsTable"), ph = el("tr", {}, el("thead", {}, pt));
  ["Pair", "Group", "Raw", "Corrected", "Wobble", "Normal band", "Normal says", "Decision"].forEach((h) => el("th", { scope: "col" }, ph, h));
  const pb = el("tbody", {}, pt), words = { exceeds_RCV: "bigger than wobble", within_RCV: "inside wobble", indeterminate_QC: "no decision" };
  D.pairs.forEach((p) => {
    const r = el("tr", {}, pb);
    [`${p.patient} ${p.from} to ${p.to}`, p.cohort, pts(p.raw), pts(p.adj), (p.band * 100).toFixed(1), (p.naive_band * 100).toFixed(1), p.naive_alarm ? "alarm" : "quiet", words[p.decision]].forEach((x) => el("td", {}, r, x));
  });
  const phi = D.headline.within_visit_negative_slope.dev.median_phi_after;
  $("#plPhi").value = phi.toFixed(1);
  $("#planner").addEventListener("input", planner); planner();
  $("#methodFoot").textContent = `Pack built from commit ${D.meta.commit}. SAM ${D.tools.sam.toLocaleString("en-US")}, Muse Spark ${D.tools.spark}, Muse Spark Open ${D.tools.spark_open} cached model calls. Data: Reichel et al. 2022, Figshare 5793482, CC BY 4.0.`;
  flowChart();
}

/* ---------- Local server only: voice note ---------- */
function wavEncode(chunks, sampleRate) {
  const len = chunks.reduce((a, c) => a + c.length, 0), buf = new Float32Array(len);
  let o = 0; chunks.forEach((c) => { buf.set(c, o); o += c.length; });
  const ds = Math.floor(sampleRate / 16000) || 1, n = Math.floor(buf.length / ds), pcm = new Int16Array(n);
  for (let i = 0; i < n; i++) { const v = Math.max(-1, Math.min(1, buf[i * ds])); pcm[i] = v < 0 ? v * 32768 : v * 32767; }
  const ab = new ArrayBuffer(44 + n * 2), d = new DataView(ab);
  const ws = (off, s) => { for (let i = 0; i < s.length; i++) d.setUint8(off + i, s.charCodeAt(i)); };
  ws(0, "RIFF"); d.setUint32(4, 36 + n * 2, true); ws(8, "WAVEfmt "); d.setUint32(16, 16, true); d.setUint16(20, 1, true); d.setUint16(22, 1, true);
  d.setUint32(24, 16000, true); d.setUint32(28, 32000, true); d.setUint16(32, 2, true); d.setUint16(34, 16, true); ws(36, "data"); d.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) d.setInt16(44 + i * 2, pcm[i], true);
  return new Uint8Array(ab);
}
function dictateButton(row, note, out) {
  let ctx, stream, buf = [], on = false;
  const b = el("button", { class: "ghost", type: "button" }, row, "Dictate note");
  b.addEventListener("click", async () => {
    if (!on) {
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { out.textContent = "Microphone unavailable. Type the note instead."; return; }
      ctx = new AudioContext(); buf = []; on = true; b.textContent = "Stop and transcribe";
      const src = ctx.createMediaStreamSource(stream), proc = ctx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = (e) => buf.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      src.connect(proc); proc.connect(ctx.destination); return;
    }
    on = false; b.textContent = "Dictate note"; stream.getTracks().forEach((t) => t.stop());
    const rate = ctx.sampleRate; ctx.close();
    let bin = ""; wavEncode(buf, rate).forEach((x) => (bin += String.fromCharCode(x)));
    const r = await (await fetch("/api/transcribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_b64: btoa(bin) }) })).json();
    if (r.status === "OK") note.value = `${note.value} ${r.text}`.trim(); else out.textContent = `Voice ${r.status}. Type the note instead.`;
  });
}

/* ---------- Boot ---------- */
function route() {
  const name = (location.hash || "#decision").slice(1), view = ["decision", "cells", "report", "method"].includes(name) ? name : "decision";
  $$(".view").forEach((v) => (v.hidden = v.id !== `view-${view}`));
  $$(".bar nav a").forEach((a) => (a.getAttribute("href") === `#${view}` ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  if (view === "decision") { heroChart(); renderPair(false); flowStrip(); }
  if (view === "method") flowChart();
  if (view === "cells" && cell && !$("#stage").dataset.played) { $("#stage").dataset.played = 1; showCell(cell, true); }
  scrollTo(0, 0);
}
async function boot() {
  try {
    const [pairs, visits, headline, flow, predictions, open, tools, meta, example, cells, reportIndex, rules, pin] = await Promise.all(
      ["pairs", "visits", "headline", "flow", "predictions", "open", "tools", "meta", "example", "cells/index", "reports/index", "rules"].map((f) => getJSON(`demo/${f}.json`))
        .concat(fetch("demo/public_key.hex").then((r) => r.text())));
    Object.assign(D, { pairs, visits, headline, flow, predictions, open, tools, meta, example, cells, reportIndex, rules, pin });
  } catch (e) {
    $("#main").textContent = `The demo data did not load (${e.message}). Reload the page.`; return;
  }
  if (location.port === "8765") {  // the local Python server; a static host never gets an /api call
    try {
      const m = await fetch("/api/meta", { cache: "no-store" });
      D.live = m.ok && !Object.values((await m.json()).live).includes("CACHED DEMO");
    } catch (e) { D.live = false; }
  }
  decisionView(); cellsView(); methodView(); await reportView();
  addEventListener("hashchange", route); route();
  let w = innerWidth;
  addEventListener("resize", () => { if (innerWidth !== w) { w = innerWidth; route(); } });
  if (reduced) $("#channelImg").src = "demo/channel.png";
}
boot();
