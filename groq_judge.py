#!/usr/bin/env python3
"""
groq_judge.py -- Groq-powered judging layer for the QC dashboard.

The Groq API key is supplied by the caller (pasted in the frontend, forwarded
per-request). It is never read from the environment or stored server-side.

Three capabilities:
  * list_models(api_key)                -> models the key can use
  * judge_content(scan, api_key, model) -> AI verdicts for the subjective text
                                            rows + an overall narrative
  * judge_images(images, api_key, model, context) -> visual QC of uploaded
                                            screenshots/designs
"""

import json
import re

import requests

GROQ_BASE = "https://api.groq.com/openai/v1"
TIMEOUT = 90

DEFAULT_TEXT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Subjective rows an LLM can judge from the fetched text evidence.
JUDGE_ROWS = {
    8:  "Headings and subheadings are correct, meaningful and free of typos.",
    9:  "Spelling, grammar and punctuation across the visible page text.",
    10: "Content reads as complete and is not accidentally duplicated or thin.",
    13: "Labels, CTA wording and contact details (emails/phones) look correct and professional.",
    23: "Each button label matches where it actually links / what it does.",
    57: "The page <title> is appropriate, descriptive and well written.",
    58: "The URL is clean, readable and human-friendly.",
}


class GroqError(Exception):
    pass


def _headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _extract_json(text):
    """Pull the first JSON object out of a model response (handles code fences)."""
    if not text:
        raise GroqError("Empty response from the model.")
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
    raise GroqError("Model did not return valid JSON.")


def _chat(api_key, model, messages, json_mode=True, temperature=0.2, max_tokens=4000):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(f"{GROQ_BASE}/chat/completions", headers=_headers(api_key),
                          json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise GroqError(f"Could not reach Groq: {e}")
    if r.status_code == 401:
        raise GroqError("Groq rejected the API key (401). Check the key you pasted.")
    if r.status_code == 404:
        raise GroqError(f"Model '{model}' not found for this key (404). Pick another model.")
    if r.status_code == 429:
        raise GroqError("Groq rate limit hit (429). Wait a moment and retry.")
    if not r.ok:
        detail = ""
        try:
            detail = r.json().get("error", {}).get("message", "")
        except Exception:
            detail = r.text[:200]
        raise GroqError(f"Groq error {r.status_code}: {detail}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def list_models(api_key):
    try:
        r = requests.get(f"{GROQ_BASE}/models", headers=_headers(api_key), timeout=30)
    except requests.RequestException as e:
        raise GroqError(f"Could not reach Groq: {e}")
    if r.status_code == 401:
        raise GroqError("Groq rejected the API key (401).")
    if not r.ok:
        raise GroqError(f"Groq error {r.status_code}.")
    ids = sorted(m["id"] for m in r.json().get("data", []))
    return ids


def judge_content(scan, api_key, model=None):
    """Ask Groq to judge the subjective text rows and write an overall narrative."""
    model = model or DEFAULT_TEXT_MODEL
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
        "You judge ONLY from the evidence given (fetched HTML text, headings, buttons, "
        "contact details). Be precise, cite concrete examples, and never invent a pass "
        "for something the evidence does not support. Respond ONLY with JSON."
    )
    user = f"""Audit this web page using the evidence below.

EVIDENCE (JSON):
{json.dumps(evidence, ensure_ascii=False)}

For each checkpoint id, decide a status of "Pass", "Fail" or "Warning" and give a
short, specific finding (name the exact typo, bad label, or issue; quote text).

Checkpoints:
{{
{rows_spec}
}}

Also write:
- "overall_summary": 2-4 sentence plain-English verdict on this page's quality.
- "top_issues": array of the most important concrete problems (strings), most severe first.
- "strengths": array of what is done well (strings).
- "content_score": integer 0-100 for overall content & copy quality.

Return EXACTLY this JSON shape:
{{
  "checkpoints": {{ "8": {{"status": "...", "finding": "..."}}, ... }},
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
    # Normalise checkpoint keys to ints.
    cps = {}
    for k, v in (result.get("checkpoints") or {}).items():
        try:
            cps[int(k)] = v
        except (ValueError, TypeError):
            continue
    result["checkpoints"] = cps
    result["model"] = model
    return result


def judge_images(images, api_key, model=None, context=""):
    """
    images: list of data URLs ("data:image/png;base64,....") or plain https URLs.
    Runs a visual QC of the design/screenshot against the visual checkpoints that
    a fetch cannot verify.
    """
    model = model or DEFAULT_VISION_MODEL
    if not images:
        raise GroqError("No images supplied.")

    checkpoints = {
        "layout": "Overall layout looks intentional, balanced and matches a professional design.",
        "alignment": "Sections, columns and content are properly aligned; nothing is off-grid.",
        "spacing": "Spacing, margins and padding are consistent and comfortable.",
        "typography": "Font sizes/weights are consistent and body text looks >=16px and readable.",
        "color_contrast": "Text has sufficient contrast against its background (WCAG-ish).",
        "overlap_overflow": "No content overlaps, is clipped, or spills outside its container.",
        "imagery": "Images are sharp, correctly proportioned (not stretched/squashed) and relevant.",
        "cta_visibility": "Primary buttons/CTAs are visible, clearly styled and obvious.",
        "responsive_feel": "Layout looks like it would hold up on smaller screens (if judgeable).",
        "placeholder": "No placeholder/lorem-ipsum text or empty/broken image boxes are visible.",
    }
    cp_spec = "\n".join(f'  "{k}": "{d}"' for k, d in checkpoints.items())
    system = (
        "You are a senior UI/UX and web QC reviewer. You are shown screenshot(s) of a "
        "web page or design. Judge what you can actually SEE. Be specific about where an "
        "issue is (top nav, hero, footer, etc.). Respond ONLY with JSON."
    )
    text_block = f"""Review the attached screenshot(s) of a web page/design for visual quality.
{('Context from the user: ' + context) if context else ''}

For each checkpoint, give "status" ("Pass"/"Fail"/"Warning") and a concrete "finding"
that names what and where. Then add an overall read.

Checkpoints:
{{
{cp_spec}
}}

Return EXACTLY this JSON:
{{
  "checkpoints": {{ "layout": {{"status":"...","finding":"..."}}, ... }},
  "overall_summary": "...",
  "top_issues": ["..."],
  "strengths": ["..."],
  "design_score": 0
}}"""

    user_content = [{"type": "text", "text": text_block}]
    for img in images[:5]:
        user_content.append({"type": "image_url", "image_url": {"url": img}})

    content = _chat(api_key, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ], max_tokens=3000)
    result = _extract_json(content)
    result["model"] = model
    return result
