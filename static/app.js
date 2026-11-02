"use strict";

const $ = (id) => document.getElementById(id);
const KEY_STORE = "qc_groq_key";
const MODEL_STORE = "qc_groq_model";

// ---- API key: frontend-only persistence (this browser) ----
const apiKeyEl = $("apiKey");
const modelEl = $("model");
try {
  const saved = localStorage.getItem(KEY_STORE);
  if (saved) apiKeyEl.value = saved;
  const savedModel = localStorage.getItem(MODEL_STORE);
  if (savedModel) modelEl.value = savedModel;
} catch (_) {}
apiKeyEl.addEventListener("input", () => {
  try { localStorage.setItem(KEY_STORE, apiKeyEl.value.trim()); } catch (_) {}
});
modelEl.addEventListener("input", () => {
  try { localStorage.setItem(MODEL_STORE, modelEl.value.trim()); } catch (_) {}
});
$("toggleKey").addEventListener("click", () => {
  apiKeyEl.type = apiKeyEl.type === "password" ? "text" : "password";
});

function apiKey() { return apiKeyEl.value.trim(); }
function model() { return modelEl.value.trim(); }

// ---- Fetch models the key can access ----
$("loadModels").addEventListener("click", async () => {
  const msg = $("keyMsg");
  msg.hidden = false; msg.className = "inline-msg"; msg.textContent = "Fetching models…";
  if (!apiKey()) { msg.className = "inline-msg bad"; msg.textContent = "Paste your Groq API key first."; return; }
  try {
    const r = await fetch("/api/models", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey: apiKey() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Failed");
    const dl = $("modelList");
    dl.innerHTML = "";
    d.models.forEach((m) => { const o = document.createElement("option"); o.value = m; dl.appendChild(o); });
    if (!model() && d.default_text) modelEl.value = d.default_text;
    msg.className = "inline-msg ok";
    msg.textContent = `${d.models.length} models available. Text default: ${d.default_text} · Vision default: ${d.default_vision}`;
  } catch (e) {
    msg.className = "inline-msg bad"; msg.textContent = String(e.message || e);
  }
});

// ---- Tabs ----
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    const tab = t.dataset.tab;
    $("panel-url").hidden = tab !== "url";
    $("panel-image").hidden = tab !== "image";
  });
});

// ---- UI helpers ----
function showLoader(text) { $("loaderText").textContent = text; $("loader").hidden = false; $("errorBox").hidden = true; }
function hideLoader() { $("loader").hidden = true; }
function showError(msg) { const e = $("errorBox"); e.textContent = msg; e.hidden = false; hideLoader(); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function statClass(status) { return ({ Pass: "pass", Fail: "fail", Warning: "warn", Info: "info", Manual: "manual", "N/A": "na" }[status] || "manual"); }

const GAUGE_COLORS = (v) => (v >= 80 ? "#22c55e" : v >= 55 ? "#f59e0b" : "#ef4444");

// =================== URL SCAN ===================
$("runUrl").addEventListener("click", async () => {
  const url = $("url").value.trim();
  if (!url) { showError("Enter a URL to QC."); return; }
  $("results").hidden = true;
  showLoader("Fetching the page and running 77 checkpoints…" + (apiKey() ? " Then asking Groq for an expert verdict…" : ""));
  try {
    const r = await fetch("/api/scan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, apiKey: apiKey(), model: model() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Scan failed");
    renderUrl(d);
  } catch (e) {
    showError(String(e.message || e));
  } finally { hideLoader(); }
});

function renderUrl(d) {
  const s = d.summary, c = s.counts;
  const ai = d.ai;
  const health = s.health;
  const parts = [];

  // Score header
  parts.push(`<section class="card">
    <div class="score-head">
      <div class="gauge" style="--val:${health};--gcol:${GAUGE_COLORS(health)}">
        <div class="g-inner"><div class="g-num">${health}</div><div class="g-lbl">HEALTH</div></div>
      </div>
      <div class="score-meta">
        <h2>${esc(d.final_url || d.url)}</h2>
        <div class="sub">HTTP ${esc(d.status_code)} · ${esc(d.load_ms)} ms · ${esc(d.page_kb)} KB${d.wordpress ? " · WordPress" : ""}${ai ? ` · AI content score ${esc(ai.content_score)}/100` : ""}</div>
        <div class="pills">
          <span class="pill pass">${c.pass} Pass</span>
          <span class="pill fail">${c.fail} Fail</span>
          <span class="pill warn">${c.warn} Warning</span>
          <span class="pill info">${c.info} Info</span>
          <span class="pill manual">${c.manual} Manual</span>
          <span class="pill na">${c.na} N/A</span>
        </div>
      </div>
    </div>`);

  if (d.ai_error) {
    parts.push(`<p class="hint" style="color:#fca5a5">AI verdict skipped: ${esc(d.ai_error)}</p>`);
  }
  if (ai) {
    parts.push(renderVerdict(ai, "AI content & copy verdict"));
  } else if (!d.ai_error) {
    parts.push(`<p class="hint">Add a Groq API key above to get an AI expert verdict on copy, headings, CTAs and contact details.</p>`);
  }
  parts.push(`</section>`);

  // Group rows by module (preserve first-seen order)
  const groups = {};
  const order = [];
  d.rows.forEach((row) => {
    if (!groups[row.module]) { groups[row.module] = []; order.push(row.module); }
    groups[row.module].push(row);
  });

  const moduleHtml = order.map((mod) => {
    const rows = groups[mod];
    const mc = { pass: 0, fail: 0, warn: 0 };
    rows.forEach((r) => { if (r.bucket === "pass") mc.pass++; else if (r.bucket === "fail") mc.fail++; else if (r.bucket === "warn") mc.warn++; });
    const hasProblem = mc.fail > 0;
    const cps = rows.map(cpRow).join("");
    return `<details class="module" ${hasProblem ? "open" : ""}>
      <summary>
        <span class="mod-title">${esc(mod)}</span>
        <span class="mod-counts">
          ${mc.fail ? `<span class="dot fail">${mc.fail}✕</span>` : ""}
          ${mc.warn ? `<span class="dot warn">${mc.warn}!</span>` : ""}
          <span class="dot pass">${mc.pass}✓</span>
        </span>
      </summary>
      ${cps}
    </details>`;
  }).join("");

  parts.push(`<section class="card"><h3 style="margin:2px 2px 6px">Checkpoint detail (77)</h3>${moduleHtml}</section>`);

  // Raw evidence
  parts.push(`<details class="raw card"><summary>Raw evidence (headings, contacts, broken links)</summary>
    <pre class="raw-json">${esc(JSON.stringify(d.raw, null, 2))}</pre></details>`);

  const res = $("results");
  res.innerHTML = parts.join("");
  res.hidden = false;
  res.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cpRow(r) {
  const aiNote = r.ai_finding
    ? `<div class="ai-note"><span class="badge-ai">AI</span> ${esc(r.ai_finding)}</div>`
    : "";
  const actual = r.actual ? `<div class="detail"><b>Result:</b> ${esc(r.actual)}</div>` : "";
  const remarks = r.remarks ? `<div class="detail">${esc(r.remarks)}</div>` : "";
  return `<div class="cp">
    <div class="sr">#${r.sr}</div>
    <div>
      <div class="cp-head">
        <span class="stat ${statClass(r.status)}">${esc(r.status)}</span>
        <span class="cp-name">${esc(r.checkpoint)}</span>
        ${r.ai ? '<span class="badge-ai">AI-judged</span>' : ""}
      </div>
      ${actual}${remarks}${aiNote}
    </div>
  </div>`;
}

function renderVerdict(ai, title) {
  const issues = (ai.top_issues || []).map((i) => `<li>${esc(i)}</li>`).join("") || "<li>None flagged.</li>";
  const strengths = (ai.strengths || []).map((i) => `<li>${esc(i)}</li>`).join("") || "<li>—</li>";
  return `<div class="verdict">
    <p><span class="badge-ai">AI</span> <b>${esc(title)}</b> <span class="muted">(${esc(ai.model || "")})</span></p>
    <p>${esc(ai.overall_summary || "")}</p>
    <div class="cols">
      <div><h4>Top issues</h4><ul>${issues}</ul></div>
      <div><h4>Strengths</h4><ul>${strengths}</ul></div>
    </div>
  </div>`;
}

// =================== IMAGE SCAN ===================
const images = []; // { url, name }
const dropzone = $("dropzone");
const fileInput = $("fileInput");

$("browseBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));

window.addEventListener("paste", (e) => {
  if ($("panel-image").hidden) return;
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const it of items) if (it.type.startsWith("image/")) handleFiles([it.getAsFile()]);
});

function handleFiles(fileList) {
  Array.from(fileList || []).forEach((f) => {
    if (!f || !f.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => { images.push({ url: reader.result, name: f.name }); renderThumbs(); };
    reader.readAsDataURL(f);
  });
}

$("addImgUrl").addEventListener("click", () => {
  const u = $("imgUrl").value.trim();
  if (!u) return;
  if (!/^https?:\/\//i.test(u)) { showError("Image URL must start with http(s)://"); return; }
  images.push({ url: u, name: u.split("/").pop() || "image" });
  $("imgUrl").value = "";
  renderThumbs();
});

function renderThumbs() {
  const t = $("thumbs");
  t.innerHTML = images.map((im, i) =>
    `<div class="thumb"><img src="${esc(im.url)}" alt="${esc(im.name)}"/><button class="rm" data-i="${i}" title="Remove">✕</button></div>`
  ).join("");
  t.querySelectorAll(".rm").forEach((b) => b.addEventListener("click", () => { images.splice(+b.dataset.i, 1); renderThumbs(); }));
}

$("runImg").addEventListener("click", async () => {
  if (!apiKey()) { showError("A Groq API key is required for image QC."); return; }
  if (!images.length) { showError("Add at least one image (upload, paste, or URL)."); return; }
  $("results").hidden = true;
  showLoader("Sending image(s) to the Groq vision model for visual QC…");
  try {
    const r = await fetch("/api/scan-image", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ images: images.map((i) => i.url), apiKey: apiKey(), model: model(), context: $("imgContext").value.trim() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Image QC failed");
    renderImage(d);
  } catch (e) {
    showError(String(e.message || e));
  } finally { hideLoader(); }
});

function renderImage(d) {
  const ai = d.ai;
  const score = ai.design_score || 0;
  const cps = ai.checkpoints || {};
  const LABELS = {
    layout: "Overall layout", alignment: "Alignment", spacing: "Spacing & padding",
    typography: "Typography", color_contrast: "Colour contrast", overlap_overflow: "Overlap / overflow",
    imagery: "Imagery", cta_visibility: "CTA visibility", responsive_feel: "Responsive feel", placeholder: "No placeholders",
  };
  const rows = Object.keys(LABELS).filter((k) => cps[k]).map((k) => {
    const v = cps[k] || {};
    const status = (v.status || "").trim();
    return `<div class="cp">
      <div class="sr">🖼</div>
      <div>
        <div class="cp-head">
          <span class="stat ${statClass(status.charAt(0).toUpperCase() + status.slice(1).toLowerCase())}">${esc(status || "—")}</span>
          <span class="cp-name">${esc(LABELS[k])}</span>
          <span class="badge-ai">AI vision</span>
        </div>
        ${v.finding ? `<div class="detail">${esc(v.finding)}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const res = $("results");
  res.innerHTML = `<section class="card">
    <div class="score-head">
      <div class="gauge" style="--val:${score};--gcol:${GAUGE_COLORS(score)}">
        <div class="g-inner"><div class="g-num">${score}</div><div class="g-lbl">DESIGN</div></div>
      </div>
      <div class="score-meta">
        <h2>Visual QC — ${d.image_count} image${d.image_count > 1 ? "s" : ""}</h2>
        <div class="sub">Reviewed by ${esc(ai.model || "")}</div>
      </div>
    </div>
    ${renderVerdict(ai, "AI visual verdict")}
  </section>
  <section class="card"><h3 style="margin:2px 2px 6px">Visual checkpoints</h3><div class="module" style="border:0">${rows}</div></section>`;
  res.hidden = false;
  res.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("printBtn").addEventListener("click", () => window.print());
