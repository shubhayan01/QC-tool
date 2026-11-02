#!/usr/bin/env python3
"""
QC Dashboard -- Flask backend.

Endpoints
  GET  /                -> the dashboard (static frontend)
  GET  /api/health      -> liveness probe
  POST /api/models      -> { apiKey } -> models the key can access
  POST /api/scan        -> { url, apiKey, model } -> full 77-point QC + AI verdicts
  POST /api/scan-image  -> { images[], apiKey, model, context } -> visual QC

The Groq API key is accepted per-request from the frontend only. It is never
persisted, logged, or read from the server environment.
"""

import os

from flask import Flask, jsonify, request, send_from_directory

import qc_core
import groq_judge

app = Flask(__name__, static_folder="static", static_url_path="")

MAX_CONTENT = 25 * 1024 * 1024  # 25 MB (room for a few screenshots)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT

# status -> coarse bucket used for scoring/colour
BUCKET = {
    "Pass": "pass", "Fail": "fail", "Warning": "warn",
    "Info": "info", "Manual": "manual", "N/A": "na",
}


def merge_ai_into_rows(scan, ai):
    """Overlay Groq verdicts onto the scanned rows and return assembled checkpoint list."""
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
                status = ai_status  # AI verdict supersedes the "Info/Manual" placeholder
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
    modules = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
        m = modules.setdefault(r["module"], {"pass": 0, "fail": 0, "warn": 0,
                                             "info": 0, "manual": 0, "na": 0, "total": 0})
        m[r["bucket"]] = m.get(r["bucket"], 0) + 1
        m["total"] += 1
    scored = counts["pass"] + counts["fail"] + counts["warn"]
    # Warnings count as half credit.
    health = round(100 * (counts["pass"] + 0.5 * counts["warn"]) / scored) if scored else 0
    return {"counts": counts, "modules": modules, "health": health, "auto_scored": scored}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/models")
def api_models():
    data = request.get_json(force=True, silent=True) or {}
    api_key = (data.get("apiKey") or "").strip()
    if not api_key:
        return jsonify({"error": "Paste your Groq API key first."}), 400
    try:
        models = groq_judge.list_models(api_key)
    except groq_judge.GroqError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"models": models,
                    "default_text": groq_judge.DEFAULT_TEXT_MODEL,
                    "default_vision": groq_judge.DEFAULT_VISION_MODEL})


@app.post("/api/scan")
def api_scan():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    api_key = (data.get("apiKey") or "").strip()
    model = (data.get("model") or "").strip() or None
    if not url:
        return jsonify({"error": "Enter a URL to QC."}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    scan = qc_core.scan_url(url)
    ai = None
    ai_error = None
    if scan.get("error"):
        return jsonify({"error": f"Could not fetch the page: {scan['error']}",
                        "url": url}), 502
    if api_key:
        try:
            ai = groq_judge.judge_content(scan, api_key, model)
        except groq_judge.GroqError as e:
            ai_error = str(e)

    rows = merge_ai_into_rows(scan, ai)
    summary = summarise(rows)
    return jsonify({
        "type": "url",
        "url": scan.get("url"),
        "final_url": scan.get("final_url"),
        "status_code": scan.get("status_code"),
        "load_ms": scan.get("load_ms"),
        "page_kb": scan.get("page_kb"),
        "wordpress": scan.get("wordpress"),
        "rows": rows,
        "summary": summary,
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
    api_key = (data.get("apiKey") or "").strip()
    model = (data.get("model") or "").strip() or None
    context = (data.get("context") or "").strip()
    if not api_key:
        return jsonify({"error": "A Groq API key is required for image QC."}), 400
    if not images:
        return jsonify({"error": "Add at least one image (upload or URL)."}), 400
    try:
        result = groq_judge.judge_images(images, api_key, model, context)
    except groq_judge.GroqError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"type": "image", "ai": result, "image_count": len(images[:5])})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=bool(os.environ.get("QC_DEBUG")))
