"use strict";

const $ = (id) => document.getElementById(id);

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

// ---- helpers ----
function showLoader(text) { $("loaderText").textContent = text; $("loader").hidden = false; $("errorBox").hidden = true; }
function hideLoader() { $("loader").hidden = true; }
function showError(msg) { const e = $("errorBox"); e.textContent = msg; e.hidden = false; hideLoader(); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function statClass(status) { return ({ Pass: "pass", Fail: "fail", Warning: "warn", Info: "info", Manual: "manual", "N/A": "na" }[status] || "manual"); }
function titleCase(s) { s = String(s || "").trim(); if (!s) return ""; if (s.toUpperCase() === "N/A") return "N/A"; return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase(); }

// =================== URL SCAN ===================
$("runUrl").addEventListener("click", runUrl);
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") runUrl(); });

async function runUrl() {
  const url = $("url").value.trim();
  if (!url) { showError("Enter a URL to QC."); return; }
  $("results").hidden = true;
  $("runUrl").disabled = true;
  showLoader("Fetching the page, running 77 checkpoints, and asking the AI auditor for a verdict…");
  try {
    const r = await fetch("/api/scan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Scan failed");
    renderUrl(d);
  } catch (e) {
    showError(String(e.message || e));
  } finally { hideLoader(); $("runUrl").disabled = false; }
}

const BUCKET_LABEL = { pass: "Pass", fail: "Fail", warn: "Warning", info: "Info", manual: "Manual", na: "N/A" };
const BUCKET_ORDER = ["fail", "warn", "pass", "info", "manual", "na"];
let currentFilter = null; // null = show all

function renderUrl(d) {
  const c = d.summary.counts;
  const ai = d.ai;
  const parts = [];

  // Header + AI verdict + filter chips (no health gauge)
  parts.push(`<section class="card">
    <div class="score-meta">
      <h2>${esc(d.final_url || d.url)}</h2>
      <div class="sub">HTTP <b>${esc(d.status_code)}</b> · ${esc(d.load_ms)} ms · ${esc(d.page_kb)} KB${d.wordpress ? " · WordPress" : ""}${ai ? ` · AI content score <b>${esc(ai.content_score)}/100</b>` : ""}</div>
    </div>`);

  if (d.ai_error) parts.push(`<p class="hint" style="color:#ffc9c9">AI verdict unavailable: ${esc(d.ai_error)}</p>`);
  if (ai) parts.push(renderVerdict(ai, "AI content &amp; copy verdict"));

  // Filter chips
  parts.push(`<div class="filterbar"><span class="hintline">Click a status to show only those checkpoints:</span>`);
  BUCKET_ORDER.forEach((b) => {
    parts.push(`<button class="chip" data-filter="${b}" data-count="${c[b] || 0}">
      <span class="dotc dc-${b}"></span>${BUCKET_LABEL[b]} <span class="n">${c[b] || 0}</span></button>`);
  });
  parts.push(`</div></section>`);

  // Checkpoints grouped by module
  const groups = {}; const order = [];
  d.rows.forEach((row) => { if (!groups[row.module]) { groups[row.module] = []; order.push(row.module); } groups[row.module].push(row); });

  const moduleHtml = order.map((mod) => {
    const rows = groups[mod];
    const mc = { pass: 0, fail: 0, warn: 0 };
    rows.forEach((r) => { if (mc[r.bucket] !== undefined) mc[r.bucket]++; });
    const cps = rows.map(cpRow).join("");
    return `<details class="module" data-buckets="${[...new Set(rows.map((r) => r.bucket))].join(" ")}" ${mc.fail ? "open" : ""}>
      <summary>
        <span class="mod-title">${esc(mod)}</span>
        <span class="mod-counts">
          ${mc.fail ? `<span class="dot fail">${mc.fail}✕</span>` : ""}
          ${mc.warn ? `<span class="dot warn">${mc.warn}!</span>` : ""}
          <span class="dot pass">${mc.pass}✓</span>
        </span>
      </summary>${cps}
    </details>`;
  }).join("");

  parts.push(`<section class="card"><h3 class="section-title">Checkpoint detail <span class="yl">(77)</span></h3>${moduleHtml}</section>`);
  parts.push(`<details class="raw card"><summary>Raw evidence (headings, contacts, broken links)</summary>
    <pre class="raw-json">${esc(JSON.stringify(d.raw, null, 2))}</pre></details>`);

  const res = $("results");
  res.innerHTML = parts.join("");
  res.hidden = false;
  currentFilter = null;
  res.querySelectorAll(".chip").forEach((ch) => ch.addEventListener("click", () => applyFilter(ch.dataset.filter)));
  res.scrollIntoView({ behavior: "smooth", block: "start" });
}

function applyFilter(bucket) {
  const res = $("results");
  if (currentFilter === bucket) bucket = null; // toggle off
  currentFilter = bucket;
  res.querySelectorAll(".chip").forEach((ch) => ch.classList.toggle("active", ch.dataset.filter === bucket));
  res.querySelectorAll(".cp").forEach((cp) => {
    const show = !bucket || cp.dataset.bucket === bucket;
    cp.classList.toggle("hidden", !show);
  });
  res.querySelectorAll(".module").forEach((m) => {
    const buckets = (m.dataset.buckets || "").split(" ");
    const has = !bucket || buckets.includes(bucket);
    m.classList.toggle("hidden", !has);
    if (bucket && has) m.open = true;
  });
}

function cpRow(r) {
  const aiNote = r.ai_finding ? `<div class="ai-note"><span class="badge-ai">AI</span> ${esc(r.ai_finding)}</div>` : "";
  const actual = r.actual ? `<div class="detail"><b>Result:</b> ${esc(r.actual)}</div>` : "";
  const remarks = r.remarks ? `<div class="detail">${esc(r.remarks)}</div>` : "";
  return `<div class="cp" data-bucket="${r.bucket}">
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
    <p><span class="badge-ai">AI</span> <b>${title}</b></p>
    <p>${esc(ai.overall_summary || "")}</p>
    <div class="cols">
      <div><h4>Top issues</h4><ul>${issues}</ul></div>
      <div><h4>Strengths</h4><ul>${strengths}</ul></div>
    </div>
  </div>`;
}

// =================== IMAGE SCAN ===================
const images = []; // { displayUrl, meta:{name,width,height,aspect,sizeKB,format,source} }
const dropzone = $("dropzone");
const fileInput = $("fileInput");

$("browseBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => handleFiles(e.target.files));
["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));
window.addEventListener("paste", (e) => {
  if ($("panel-image").hidden) return;
  const items = e.clipboardData && e.clipboardData.items; if (!items) return;
  for (const it of items) if (it.type.startsWith("image/")) handleFiles([it.getAsFile()]);
});

function measure(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => resolve({ width: null, height: null });
    img.src = url;
  });
}

async function handleFiles(fileList) {
  for (const f of Array.from(fileList || [])) {
    if (!f || !f.type.startsWith("image/")) continue;
    const displayUrl = URL.createObjectURL(f);
    const dims = await measure(displayUrl);
    images.push({
      displayUrl,
      meta: {
        name: f.name, source: "upload",
        format: (f.type.split("/")[1] || "").toUpperCase(),
        sizeKB: Math.round(f.size / 1024),
        width: dims.width, height: dims.height,
        aspect: dims.width && dims.height ? +(dims.width / dims.height).toFixed(2) : null,
      },
    });
    renderThumbs();
  }
}

$("addImgUrl").addEventListener("click", async () => {
  const u = $("imgUrl").value.trim();
  if (!u) return;
  if (!/^https?:\/\//i.test(u)) { showError("Image URL must start with http(s)://"); return; }
  const dims = await measure(u);
  const ext = (u.split(".").pop() || "").split(/[?#]/)[0].toUpperCase();
  images.push({
    displayUrl: u,
    meta: {
      name: u.split("/").pop() || "image", source: "url",
      format: ext.length <= 5 ? ext : "?", sizeKB: null,
      width: dims.width, height: dims.height,
      aspect: dims.width && dims.height ? +(dims.width / dims.height).toFixed(2) : null,
    },
  });
  $("imgUrl").value = "";
  renderThumbs();
});

function renderThumbs() {
  const t = $("thumbs");
  t.innerHTML = images.map((im, i) => {
    const m = im.meta;
    const dims = m.width ? `${m.width}×${m.height}` : "dims?";
    const size = m.sizeKB != null ? ` · ${m.sizeKB}KB` : "";
    return `<div class="thumb">
      <div class="imgwrap"><img src="${esc(im.displayUrl)}" alt="${esc(m.name)}"/></div>
      <div class="meta">${dims}${size}<br>${esc(m.format || "")}</div>
      <button class="rm" data-i="${i}" title="Remove">✕</button>
    </div>`;
  }).join("");
  t.querySelectorAll(".rm").forEach((b) => b.addEventListener("click", () => { images.splice(+b.dataset.i, 1); renderThumbs(); }));
}

$("runImg").addEventListener("click", async () => {
  if (!images.length) { showError("Add at least one image (upload, paste, or URL)."); return; }
  $("results").hidden = true;
  $("runImg").disabled = true;
  showLoader("Measuring each image and asking the AI reviewer to assess them for web use…");
  try {
    const r = await fetch("/api/scan-image", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ images: images.map((i) => i.meta), context: $("imgContext").value.trim() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Image QC failed");
    renderImage(d);
  } catch (e) {
    showError(String(e.message || e));
  } finally { hideLoader(); $("runImg").disabled = false; }
});

function renderImage(d) {
  const ai = d.ai;
  const imgResults = ai.images || {};
  const rows = images.map((im, i) => {
    const v = imgResults[i] || {};
    const status = titleCase(v.status);
    const m = im.meta;
    const specs = `${m.width ? m.width + "×" + m.height + "px" : "dimensions unknown"}` +
      `${m.aspect ? " · aspect " + m.aspect : ""}${m.sizeKB != null ? " · " + m.sizeKB + " KB" : ""}${m.format ? " · " + m.format : ""}`;
    return `<div class="cp">
      <div class="sr"><img src="${esc(im.displayUrl)}" alt="" style="width:36px;height:28px;object-fit:cover;border-radius:5px"/></div>
      <div>
        <div class="cp-head">
          <span class="stat ${statClass(status)}">${esc(status || "—")}</span>
          <span class="cp-name">${esc(m.name)}</span>
          <span class="badge-ai">AI</span>
        </div>
        <div class="detail"><b>Measured:</b> ${esc(specs)}</div>
        ${v.finding ? `<div class="ai-note"><span class="badge-ai">AI</span> ${esc(v.finding)}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const res = $("results");
  res.innerHTML = `<section class="card">
    <div class="score-meta">
      <h2>Image QC — ${d.image_count} image${d.image_count > 1 ? "s" : ""}</h2>
      <div class="sub">AI content score <b>${esc(ai.design_score || 0)}/100</b></div>
    </div>
    ${renderVerdict(ai, "AI image verdict")}
  </section>
  <section class="card"><h3 class="section-title">Per-image assessment</h3><div>${rows}</div></section>`;
  res.hidden = false;
  res.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("printBtn").addEventListener("click", () => window.print());
