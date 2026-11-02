#!/usr/bin/env python3
"""
Justwords QC tool -- Flask backend.

Endpoints
  GET  /                -> the dashboard (static frontend)
  GET  /api/health      -> liveness probe
  POST /api/scan        -> { url } -> full 77-point QC + AI verdict
  POST /api/scan-image  -> { images[], context } -> AI assessment of image metrics

The AI key and model are configured on the server (env vars, with a built-in
default) so the tool works out of the box with no setup in the UI.
"""

import os

from flask import Flask, jsonify, request, send_from_directory

import qc_core
import ai_engine

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# ---- AI configuration (server-side; no key is ever committed) ----
# Order of precedence: GROQ_API_KEY env var (set this on Render) -> a local
# gitignored file next to this app ("groq_key.txt") for local development.
def _load_key():
    env = os.environ.get("GROQ_API_KEY", "").strip()
    if env:
        return env
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq_key.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""

AI_KEY = _load_key()
AI_MODEL = os.environ.get("QC_MODEL", "openai/gpt-oss-120b")

BUCKET = {
    "Pass": "pass", "Fail": "fail", "Warning": "warn",
    "Info": "info", "Manual": "manual", "N/A": "na",
}


def merge_ai_into_rows(scan, ai):
    meta = {m["sr"]: m for m in qc_core.checklist_meta()}
    ai_cps = (ai or {}).get("checkpoints", {}) if ai else {}
    rows_out = []
    for sr in sorted(meta):
        base = scan["rows"].get(sr, {})
        status = base.get("status", "Manual")
        actual = base.get("actual", "")
        remarks = base.get("remarks", "")
        ai_entry = ai_cps.get(sr)
        ai_status = None
        ai_finding = None
        if ai_entry and isinstance(ai_entry, dict):
            ai_status = (ai_entry.get("status") or "").strip().title() or None
            ai_finding = ai_entry.get("finding")
            if ai_status in ("Pass", "Fail", "Warning"):
                status = ai_status
        rows_out.append({
            "sr": sr,
            "module": meta[sr]["module"],
            "checkpoint": meta[sr]["checkpoint"],
            "mode": meta[sr]["mode"],
            "status": status,
            "bucket": BUCKET.get(status, "manual"),
            "actual": actual,
            "remarks": remarks,
            "ai": bool(ai_entry),
            "ai_status": ai_status,
            "ai_finding": ai_finding,
        })
    return rows_out


def summarise(rows):
    counts = {"pass": 0, "fail": 0, "warn": 0, "info": 0, "manual": 0, "na": 0}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    return {"counts": counts}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/scan")
def api_scan():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Enter a URL to QC."}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    scan = qc_core.scan_url(url)
    if scan.get("error"):
        return jsonify({"error": f"Could not fetch the page: {scan['error']}", "url": url}), 502

    ai, ai_error = None, None
    if not AI_KEY:
        ai_error = "AI key not configured on the server (set the GROQ_API_KEY environment variable)."
    else:
        try:
            ai = ai_engine.judge_content(scan, AI_KEY, AI_MODEL)
        except ai_engine.AIError as e:
            ai_error = str(e)

    rows = merge_ai_into_rows(scan, ai)
    return jsonify({
        "type": "url",
        "url": scan.get("url"),
        "final_url": scan.get("final_url"),
        "status_code": scan.get("status_code"),
        "load_ms": scan.get("load_ms"),
        "page_kb": scan.get("page_kb"),
        "wordpress": scan.get("wordpress"),
        "rows": rows,
        "summary": summarise(rows),
        "ai": ai,
        "ai_error": ai_error,
        "raw": {
            "title": scan["raw"].get("title"),
            "meta_description": scan["raw"].get("meta_description"),
            "emails": scan["raw"].get("emails"),
            "phones": scan["raw"].get("phones"),
            "broken_links": scan["raw"].get("broken_links"),
            "headings": scan["raw"].get("headings", [])[:40],
        },
    })


@app.post("/api/scan-image")
def api_scan_image():
    data = request.get_json(force=True, silent=True) or {}
    images = data.get("images") or []
    context = (data.get("context") or "").strip()
    if not images:
        return jsonify({"error": "Add at least one image."}), 400
    if not AI_KEY:
        return jsonify({"error": "AI key not configured on the server (set GROQ_API_KEY)."}), 400
    try:
        result = ai_engine.judge_images(images, AI_KEY, AI_MODEL, context)
    except ai_engine.AIError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"type": "image", "ai": result, "image_count": len(images)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=bool(os.environ.get("QC_DEBUG")))
