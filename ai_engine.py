#!/usr/bin/env python3
"""
ai_engine.py -- AI judging layer for the Justwords QC tool.

Talks to an OpenAI-compatible chat endpoint. The key and model are supplied by
the server (app.py); this module takes them as arguments.

  * judge_content(scan, api_key, model)      -> verdict for subjective text rows
  * judge_images(images_meta, api_key, model, context) -> assessment of image
                                                 technical metrics for web use
"""

import json
import re

import requests

API_BASE = "https://api.groq.com/openai/v1"
TIMEOUT = 90

# Rows the AI can judge from the fetched text evidence.
JUDGE_ROWS = {
    8:  "Headings and subheadings are correct, meaningful and free of typos.",
    9:  "Spelling, grammar and punctuation across the visible page text.",
    10: "Content reads as complete and is not accidentally duplicated or thin.",
    13: "Labels, CTA wording and contact details (emails/phones) look correct and professional.",
    23: "Each button label matches where it actually links / what it does.",
    57: "The page <title> is appropriate, descriptive and well written.",
    58: "The URL is clean, readable and human-friendly.",
}


class AIError(Exception):
    pass


def _headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _extract_json(text):
    if not text:
        raise AIError("Empty response from the AI model.")
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise AIError("The AI model did not return valid JSON.")


def _chat(api_key, model, messages, json_mode=True, temperature=0.15, max_tokens=4000):
    payload = {"model": model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(f"{API_BASE}/chat/completions", headers=_headers(api_key),
                          json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise AIError(f"Could not reach the AI service: {e}")
    if r.status_code == 401:
        raise AIError("The AI service rejected the configured key (401).")
    if r.status_code == 404:
        raise AIError(f"Model '{model}' is not available (404).")
    if r.status_code == 429:
        raise AIError("AI rate limit reached (429). Try again in a moment.")
    if not r.ok:
        detail = ""
        try:
            detail = r.json().get("error", {}).get("message", "")
        except Exception:
            detail = r.text[:200]
        raise AIError(f"AI service error {r.status_code}: {detail}")
    return r.json()["choices"][0]["message"]["content"]


def judge_content(scan, api_key, model):
    raw = scan.get("raw", {})
    evidence = {
        "url": scan.get("final_url") or scan.get("url"),
        "title": raw.get("title", ""),
        "meta_description": raw.get("meta_description", ""),
        "headings": raw.get("headings", [])[:40],
        "buttons": raw.get("buttons", [])[:30],
        "emails": raw.get("emails", []),
        "phones": raw.get("phones", []),
        "broken_links": raw.get("broken_links", [])[:10],
        "images_total": raw.get("images_total", 0),
        "is_wordpress": raw.get("wordpress", False),
        "page_text_excerpt": raw.get("page_text", "")[:5000],
    }
    rows_spec = "\n".join(f'  "{sr}": "{desc}"' for sr, desc in JUDGE_ROWS.items())
    system = (
        "You are a meticulous senior website QC (quality-control) auditor. "
        "Judge ONLY from the evidence provided. Be precise, quote concrete examples "
        "(the exact typo, bad label, awkward sentence), and never invent a pass for "
        "something the evidence does not support. If the evidence is clean, say Pass. "
        "Respond ONLY with JSON."
    )
    user = f"""Audit this web page using the evidence below.

EVIDENCE (JSON):
{json.dumps(evidence, ensure_ascii=False)}

For each checkpoint id, decide a status of "Pass", "Fail" or "Warning" and give a
short, specific finding. Quote the exact text you are flagging.

Checkpoints:
{{
{rows_spec}
}}

Also provide:
- "overall_summary": 2-4 sentence plain-English verdict on this page's quality.
- "top_issues": array of the most important concrete problems (strings), worst first.
- "strengths": array of what is done well (strings).
- "content_score": integer 0-100 for overall content & copy quality.

Return EXACTLY this JSON shape:
{{
  "checkpoints": {{ "8": {{"status":"...","finding":"..."}}, ... }},
  "overall_summary": "...",
  "top_issues": ["..."],
  "strengths": ["..."],
  "content_score": 0
}}"""
    content = _chat(api_key, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    result = _extract_json(content)
    cps = {}
    for k, v in (result.get("checkpoints") or {}).items():
        try:
            cps[int(k)] = v
        except (ValueError, TypeError):
            continue
    result["checkpoints"] = cps
    result["model"] = model
    return result


def judge_images(images_meta, api_key, model, context=""):
    """
    images_meta: list of dicts the frontend measured, e.g.
      {name, width, height, aspect, sizeKB, format, source}
    The AI assesses each image's fitness for web use (resolution, file weight,
    aspect/distortion risk, format) and gives an overall verdict.
    """
    if not images_meta:
        raise AIError("No image details supplied.")
    system = (
        "You are a senior web QC and performance reviewer assessing images for use "
        "on a website, from their technical metadata (you cannot see the pixels). "
        "Apply web best practice: heroes/banners want >=1600px wide; content images "
        "720-1200px; file weight ideally <300KB and a warning sign over ~500KB; modern "
        "formats (WebP/AVIF) preferred over PNG/JPEG for photos; extreme aspect ratios "
        "or tiny dimensions risk stretching/blur. Respond ONLY with JSON."
    )
    user = f"""Assess these image(s) for website quality.
{('Context: ' + context) if context else ''}

IMAGES (JSON):
{json.dumps(images_meta, ensure_ascii=False)}

For EACH image (by its index, starting at 0), give:
- "status": "Pass" / "Fail" / "Warning"
- "finding": concrete note on resolution, file weight, format and aspect fitness.

Then provide an overall read.

Return EXACTLY this JSON:
{{
  "images": {{ "0": {{"status":"...","finding":"..."}}, ... }},
  "overall_summary": "...",
  "top_issues": ["..."],
  "strengths": ["..."],
  "design_score": 0
}}"""
    content = _chat(api_key, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], max_tokens=3000)
    result = _extract_json(content)
    imgs = {}
    for k, v in (result.get("images") or {}).items():
        try:
            imgs[int(k)] = v
        except (ValueError, TypeError):
            continue
    result["images"] = imgs
    result["model"] = model
    return result
