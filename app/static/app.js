"use strict";

/* EHR Data Quality Checker — frontend logic (vanilla JS, no build step). */

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const fmt = (n) => Number(n).toLocaleString("en-US");
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const DIMENSIONS = ["completeness", "validity", "uniqueness", "consistency", "integrity"];

let activeFilter = "all";
let lastResults = [];

/* ---------------------------------------------------------------- bootstrap */
async function init() {
  setupTabs();
  await loadProfiles();
  $("#run-sample").addEventListener("click", runSample);
  $("#run-audit").addEventListener("click", runAudit);
  $("#run-upload").addEventListener("click", runUpload);
  $("#run-interop").addEventListener("click", runInterop);
  $("#run-history").addEventListener("click", runHistory);
  $("#refresh-history").addEventListener("click", loadHistoryDatasets);
  // Load available history datasets when the History tab is opened.
  document.querySelector('.tab[data-tab="history"]')
    .addEventListener("click", loadHistoryDatasets);
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");
      const name = tab.dataset.tab;
      document.querySelectorAll(".tabpane").forEach((p) =>
        p.classList.toggle("is-hidden", p.dataset.pane !== name)
      );
    });
  });
}

async function loadProfiles() {
  try {
    const res = await fetch("/api/profiles");
    const profiles = await res.json();
    const sampleSel = $("#sample-dataset");
    const uploadSel = $("#upload-dataset");
    profiles.forEach((p) => {
      sampleSel.append(new Option(`${p.title} (${p.rule_count} rules)`, p.key));
      uploadSel.append(new Option(p.title, p.key));
    });
    sampleSel.value = "patients";
  } catch (e) {
    showStatus("Could not reach the API. Is the server running?", "err");
  }
}

/* ------------------------------------------------------------------ helpers */
function showStatus(msg, kind = "info") {
  const s = $("#status");
  s.className = `status ${kind}`;
  s.textContent = msg;
  s.classList.remove("is-hidden");
}
function hideStatus() { $("#status").classList.add("is-hidden"); }
function hideAll() {
  $("#empty").classList.add("is-hidden");
  $("#report").classList.add("is-hidden");
  $("#audit").classList.add("is-hidden");
}
function busy(btn, on) {
  btn.disabled = on;
  if (on) {
    btn.dataset.label = btn.innerHTML;
    btn.innerHTML = `<span class="spin"></span>${btn.dataset.label}`;
  } else if (btn.dataset.label) {
    btn.innerHTML = btn.dataset.label;
  }
}
async function apiError(res) {
  let detail = `Request failed (${res.status}).`;
  try { detail = (await res.json()).detail || detail; } catch (e) {}
  return detail;
}

/* -------------------------------------------------------------- run actions */
async function runSample() {
  const name = $("#sample-dataset").value;
  const variant = $("#sample-variant").value;
  const btn = $("#run-sample");
  busy(btn, true);
  hideStatus();
  try {
    const res = await fetch(`/api/check/sample?name=${name}&variant=${variant}`, { method: "POST" });
    if (!res.ok) throw new Error(await apiError(res));
    renderReport(await res.json());
  } catch (e) {
    showStatus(e.message, "err");
  } finally {
    busy(btn, false);
  }
}

async function runUpload() {
  const file = $("#upload-file").files[0];
  const btn = $("#run-upload");
  if (!file) { showStatus("Choose a CSV file first.", "err"); return; }
  const dataset = $("#upload-dataset").value;
  const form = new FormData();
  form.append("file", file);
  const url = dataset ? `/api/check?dataset=${dataset}` : "/api/check";
  busy(btn, true);
  hideStatus();
  try {
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) throw new Error(await apiError(res));
    renderReport(await res.json());
  } catch (e) {
    showStatus(e.message, "err");
  } finally {
    busy(btn, false);
  }
}

async function runAudit() {
  const variant = $("#sample-variant").value;
  const btn = $("#run-audit");
  busy(btn, true);
  hideStatus();
  try {
    const res = await fetch(`/api/audit?variant=${variant}`);
    if (!res.ok) throw new Error(await apiError(res));
    renderAudit(await res.json());
  } catch (e) {
    showStatus(e.message, "err");
  } finally {
    busy(btn, false);
  }
}

async function runInterop() {
  const file = $("#interop-file").files[0];
  const btn = $("#run-interop");
  if (!file) { showStatus("Choose a FHIR or HL7 file first.", "err"); return; }
  const fmt = $("#interop-format").value;
  const url = fmt === "hl7" ? "/api/check/hl7" : "/api/check/fhir";
  const form = new FormData();
  form.append("file", file);
  busy(btn, true);
  hideStatus();
  try {
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) throw new Error(await apiError(res));
    renderAudit(await res.json());
  } catch (e) {
    showStatus(e.message, "err");
  } finally {
    busy(btn, false);
  }
}

async function loadHistoryDatasets() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const sel = $("#history-dataset");
    if (!data.enabled) {
      sel.innerHTML = "";
      sel.append(new Option("— history disabled —", ""));
      showStatus("History is disabled on this server (EHR_HISTORY=off).", "info");
      return;
    }
    const current = sel.value;
    sel.innerHTML = "";
    if (data.datasets.length === 0) {
      sel.append(new Option("— run a check first —", ""));
    } else {
      data.datasets.forEach((d) => sel.append(new Option(d, d)));
      if (data.datasets.includes(current)) sel.value = current;
    }
  } catch (e) {
    showStatus("Could not load history.", "err");
  }
}

async function runHistory() {
  const dataset = $("#history-dataset").value;
  const btn = $("#run-history");
  if (!dataset) { showStatus("No history yet — run a check first.", "info"); return; }
  busy(btn, true);
  hideStatus();
  try {
    const [tRes, hRes] = await Promise.all([
      fetch(`/api/history/trends?dataset=${dataset}`),
      fetch(`/api/history?dataset=${dataset}&limit=20`),
    ]);
    if (!tRes.ok) throw new Error(await apiError(tRes));
    if (!hRes.ok) throw new Error(await apiError(hRes));
    renderTrends(dataset, await tRes.json(), await hRes.json());
  } catch (e) {
    showStatus(e.message, "err");
  } finally {
    busy(btn, false);
  }
}

/* -------------------------------------------------------------- score gauge */
function scoreColor(score) {
  if (score >= 90) return "#16a34a";
  if (score >= 75) return "#d97706";
  return "#dc2626";
}
function gauge(score) {
  const r = 63, c = 2 * Math.PI * r;
  const offset = c * (1 - score / 100);
  return `
    <div class="gauge">
      <svg viewBox="0 0 150 150" width="150" height="150" role="img" aria-label="Quality score ${score} out of 100">
        <circle class="gauge-ring-bg" cx="75" cy="75" r="${r}"></circle>
        <circle class="gauge-ring" cx="75" cy="75" r="${r}"
          stroke="${scoreColor(score)}" stroke-dasharray="${c}" stroke-dashoffset="${offset}"></circle>
      </svg>
      <div class="gauge-label">
        <span class="gauge-score" style="color:${scoreColor(score)}">${score}</span>
      </div>
    </div>`;
}

/* ------------------------------------------------------------- render report */
function renderReport(report) {
  hideAll();
  activeFilter = "all";
  lastResults = report.results;
  const s = report.summary;
  const root = $("#report");
  root.innerHTML = "";

  const head = el("div", "report-head");
  head.append(
    el("div", "report-title",
      `<h2>${esc(report.dataset_title)}</h2>
       <p>${fmt(report.row_count)} rows · ${report.column_count} columns ·
       ${report.auto_detected ? "auto-detected · " : ""}${report.variant ? esc(report.variant) + " sample" : "uploaded file"}</p>`),
    el("span", "badge", `Grade ${s.grade}`)
  );
  root.append(head);

  const overview = el("div", "overview");
  const scoreCard = el("div", "score-card");
  scoreCard.innerHTML = gauge(s.score) +
    `<div class="score-caption">Weighted quality score</div>`;
  overview.append(scoreCard);

  const cards = el("div", "cards");
  cards.append(
    statCard(s.errors, "Errors", s.errors ? "err" : "ok", "must-fix issues"),
    statCard(s.warnings, "Warnings", s.warnings ? "warn" : "ok", "review recommended"),
    statCard(`${s.clean_row_pct}%`, "Clean rows", s.clean_row_pct === 100 ? "ok" : "", `${fmt(s.clean_rows)} of ${fmt(report.row_count)}`),
    statCard(`${s.rules_passed}/${s.rules_run}`, "Rules passed", "", `${s.rules_skipped} skipped`)
  );
  overview.append(cards);
  root.append(overview);

  root.append(renderDimensions(report.dimensions));
  root.append(renderFindings(report.results));
  root.classList.remove("is-hidden");
  root.scrollIntoView({ behavior: "smooth", block: "start" });
}

function statCard(value, label, cls, sub) {
  const c = el("div", `card ${cls || ""}`);
  c.innerHTML = `<div class="k">${esc(label)}</div><div class="v">${esc(value)}</div>` +
    (sub ? `<div class="sub">${esc(sub)}</div>` : "");
  return c;
}

function renderDimensions(dims) {
  const box = el("div", "dims");
  box.append(el("h3", null, "Quality dimensions"));
  DIMENSIONS.forEach((dim) => {
    const d = dims[dim] || { score: null, rules: 0, checked: 0, failed: 0 };
    const row = el("div", "dim");
    const score = d.score;
    if (d.rules === 0 || score === null) row.classList.add("skipped");
    const pct = score === null ? 0 : score;
    row.innerHTML =
      `<span class="dim-name">${dim}</span>
       <div class="dim-track"><div class="dim-fill" style="width:${pct}%;background:${score === null ? "#cbd5e1" : scoreColor(pct)}"></div></div>
       <span class="dim-meta">${score === null ? "n/a" : score + "%"} · ${fmt(d.failed)} flagged</span>`;
    box.append(row);
  });
  return box;
}

/* ------------------------------------------------------------- findings list */
function renderFindings(results) {
  const box = el("div", "findings");
  box.append(el("h3", null, "Findings"));

  const toolbar = el("div", "findings-toolbar");
  const counts = {
    all: results.length,
    failed: results.filter((r) => r.status === "failed").length,
    passed: results.filter((r) => r.status === "passed").length,
    skipped: results.filter((r) => r.status === "skipped").length,
  };
  [["all", "All"], ["failed", "Failed"], ["passed", "Passed"], ["skipped", "Skipped"]].forEach(([key, label]) => {
    const chip = el("button", "chip" + (activeFilter === key ? " is-active" : ""), `${label} (${counts[key]})`);
    chip.addEventListener("click", () => {
      activeFilter = key;
      const fresh = renderFindings(lastResults);
      box.replaceWith(fresh);
    });
    toolbar.append(chip);
  });
  box.append(toolbar);

  const table = el("table", "results");
  table.innerHTML =
    `<thead><tr>
      <th>Status</th><th>Dimension</th><th>Rule</th><th>Flagged</th><th>Detail</th>
    </tr></thead>`;
  const tbody = el("tbody");

  const shown = results.filter((r) => activeFilter === "all" || r.status === activeFilter);
  // Failed first, errors before warnings, biggest impact first.
  shown.sort((a, b) => {
    const rank = (r) => (r.status === "failed" ? 0 : r.status === "passed" ? 1 : 2);
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    if (a.severity !== b.severity) return a.severity === "error" ? -1 : 1;
    return b.failed - a.failed;
  });

  if (shown.length === 0) {
    tbody.append(el("tr", null, `<td colspan="5" style="color:var(--muted);padding:18px">No rules in this view.</td>`));
  }

  shown.forEach((r) => {
    const tr = el("tr", "row-rule");
    const sevClass = r.status === "passed" ? "pass" : r.status === "skipped" ? "skip" : r.severity;
    const sevLabel = r.status === "passed" ? "Pass" : r.status === "skipped" ? "Skipped" : r.severity;
    const hasSample = r.sample && r.sample.length > 0;
    const caret = hasSample ? "▸" : "";
    const flagged = r.status === "skipped"
      ? "—"
      : `<span class="${r.failed ? "count-bad" : ""}">${fmt(r.failed)}</span> / ${fmt(r.checked)}`;
    tr.innerHTML =
      `<td><span class="sev ${sevClass}">${esc(sevLabel)}</span></td>
       <td><span class="cat-tag">${esc(r.category)}</span></td>
       <td class="msg"><span class="toggle-caret">${caret}</span>${esc(r.title)}</td>
       <td class="count-cell">${flagged}</td>
       <td class="msg">${esc(r.status === "skipped" ? (r.skip_reason || r.message) : r.message)}</td>`;
    tbody.append(tr);

    if (hasSample) {
      const sampleTr = el("tr", "sample-row is-hidden");
      const td = el("td");
      td.colSpan = 5;
      td.append(sampleRows(r.sample));
      sampleTr.append(td);
      tbody.append(sampleTr);
      tr.addEventListener("click", () => {
        sampleTr.classList.toggle("is-hidden");
        const c = tr.querySelector(".toggle-caret");
        c.textContent = sampleTr.classList.contains("is-hidden") ? "▸" : "▾";
      });
    }
  });

  table.append(tbody);
  box.append(table);
  return box;
}

function sampleRows(sample) {
  const wrap = el("div", "sample-wrap");
  wrap.append(el("div", "label", `Sample of offending rows (showing ${sample.length}):`));
  const cols = Object.keys(sample[0]);
  const table = el("table", "sample");
  const thead = "<thead><tr>" + cols.map((c) =>
    `<th>${c === "_line" ? "CSV line" : esc(c)}</th>`).join("") + "</tr></thead>";
  const body = sample.map((row) =>
    "<tr>" + cols.map((c) => {
      const v = row[c];
      if (c === "_line") return `<td class="line-col">${esc(v)}</td>`;
      return v === null ? `<td class="null">null</td>` : `<td>${esc(v)}</td>`;
    }).join("") + "</tr>"
  ).join("");
  table.innerHTML = thead + "<tbody>" + body + "</tbody>";
  wrap.append(table);
  return wrap;
}

/* --------------------------------------------------------------- render audit */
const AUDIT_TITLES = { audit: "Full database audit", fhir: "FHIR bundle audit", hl7v2: "HL7 v2 audit" };

function renderAudit(result) {
  hideAll();
  const root = $("#audit");
  root.innerHTML = "";
  const a = result.aggregate;
  const title = AUDIT_TITLES[result.source] || "Audit";
  const provenance = result.format
    ? `${esc(result.format)} · ${a.tables} tables derived`
    : `${esc(result.variant || "")} variant · ${a.tables} tables`;

  const head = el("div", "audit-head");
  head.innerHTML =
    `<h2>${title}</h2>
     <p>${provenance} · ${fmt(a.rows)} rows ·
     <strong style="color:var(--err)">${fmt(a.errors)}</strong> errors,
     <strong style="color:var(--warn)">${fmt(a.warnings)}</strong> warnings ·
     average score ${a.score}</p>`;
  root.append(head);

  const grid = el("div", "audit-grid");
  result.tables.forEach((report) => {
    const s = report.summary;
    const card = el("button", "audit-card");
    const ok = s.errors === 0;
    card.innerHTML =
      `<div class="name">${esc(report.dataset_title)}
        <span class="pill ${ok ? "ok" : "bad"}">${s.score}</span></div>
       <div class="meta">${fmt(report.row_count)} rows · ${s.errors} errors · ${s.warnings} warnings ·
       ${s.rules_skipped} skipped</div>`;
    card.addEventListener("click", () => {
      renderReport(report);
      const back = el("button", "back-link", "‹ Back to audit");
      back.addEventListener("click", () => renderAudit(result));
      $("#report").prepend(back);
    });
    grid.append(card);
  });
  root.append(grid);
  root.classList.remove("is-hidden");
  root.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* --------------------------------------------------------------- render trends */
function renderTrends(dataset, trends, history) {
  hideAll();
  const root = $("#audit");
  root.innerHTML = "";
  const points = trends.points || [];

  const head = el("div", "audit-head");
  head.innerHTML =
    `<h2>Quality trend — ${esc(dataset)}</h2>
     <p>${points.length} run${points.length === 1 ? "" : "s"} recorded ·
     summary-only history (no patient data stored)</p>`;
  root.append(head);

  if (points.length === 0) {
    root.append(el("p", "hint", "No history for this dataset yet. Run a check, then come back."));
    root.classList.remove("is-hidden");
    return;
  }

  const card = el("div", "card");
  card.style.padding = "18px 20px";
  card.innerHTML = trendChartSVG(points);
  root.append(card);

  const recent = history.records || [];
  if (recent.length) {
    const box = el("div", "findings");
    box.style.marginTop = "18px";
    box.append(el("h3", null, "Recent runs"));
    const table = el("table", "results");
    table.innerHTML =
      `<thead><tr><th>When (UTC)</th><th>Source</th><th>Score</th>
       <th>Errors</th><th>Warnings</th><th>Rows</th></tr></thead>`;
    const tb = el("tbody");
    recent.forEach((r) => {
      const tr = el("tr");
      tr.innerHTML =
        `<td>${esc((r.created_at || "").replace("T", " ").slice(0, 16))}</td>
         <td><span class="cat-tag">${esc(r.source)}</span></td>
         <td><strong style="color:${scoreColor(r.score)}">${r.score}</strong></td>
         <td class="${r.errors ? "count-bad" : ""}">${fmt(r.errors)}</td>
         <td>${fmt(r.warnings)}</td>
         <td>${fmt(r.row_count)}</td>`;
      tb.append(tr);
    });
    table.append(tb);
    box.append(table);
    root.append(box);
  }

  root.classList.remove("is-hidden");
  root.scrollIntoView({ behavior: "smooth", block: "start" });
}

function trendChartSVG(points) {
  const W = 680, H = 220, padL = 44, padR = 16, padT = 16, padB = 34;
  const scores = points.map((p) => Number(p.score));
  const lo = Math.min(...scores);
  const yMax = 100;
  const yMin = lo >= 100 ? 90 : Math.max(0, Math.floor(lo - 3));
  const n = points.length;
  const x = (i) => (n === 1 ? padL + (W - padL - padR) / 2 : padL + (i * (W - padL - padR)) / (n - 1));
  const y = (s) => padT + ((yMax - s) / (yMax - yMin)) * (H - padT - padB);

  const ticks = [yMax, Math.round((yMax + yMin) / 2), yMin];
  const grid = ticks.map((t) =>
    `<line x1="${padL}" y1="${y(t).toFixed(1)}" x2="${W - padR}" y2="${y(t).toFixed(1)}" stroke="#e2e8f0"/>` +
    `<text x="${padL - 8}" y="${(y(t) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#64748b">${t}</text>`
  ).join("");

  const poly = points.map((p, i) => `${x(i).toFixed(1)},${y(Number(p.score)).toFixed(1)}`).join(" ");
  const line = n > 1 ? `<polyline points="${poly}" fill="none" stroke="#0f766e" stroke-width="2"/>` : "";
  const dots = points.map((p, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(Number(p.score)).toFixed(1)}" r="4" fill="${scoreColor(Number(p.score))}">` +
    `<title>${esc((p.created_at || "").slice(0, 16))}: ${p.score}</title></circle>`
  ).join("");

  const lbl = (p) => esc((p.created_at || "").slice(5, 16).replace("T", " "));
  const xlabels =
    `<text x="${x(0).toFixed(1)}" y="${H - 10}" font-size="11" fill="#64748b" text-anchor="start">${lbl(points[0])}</text>` +
    (n > 1 ? `<text x="${x(n - 1).toFixed(1)}" y="${H - 10}" font-size="11" fill="#64748b" text-anchor="end">${lbl(points[n - 1])}</text>` : "");

  return `<div style="font-size:13px;color:var(--muted);margin-bottom:8px">Quality score over time</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Quality score over time">
    ${grid}${line}${dots}${xlabels}</svg>`;
}

document.addEventListener("DOMContentLoaded", init);
