---
name: wordpress-qc
description: >-
  Run a QC (quality-control) pass on one or more WordPress (or any) web pages
  and produce an Excel/CSV report. Fetches each URL, runs 70+ automated
  checkpoints (broken links & 404s, images & alt text, titles/meta/H1 &
  heading hierarchy, placeholder text, 16px font size, HTTPS/mixed content,
  forms, responsive signals, footer/contact links, copyright year, SEO tags),
  judges the subjective checkpoints from the fetched content, and writes a
  report with the columns Sr. No. | Module | Checkpoint | Status | Actual
  Result | Remarks (one sheet per URL). Use when the user says "QC", "QC these
  links", "test these pages", "website quality check", "check this site",
  "run a QC report", or pastes a list of URLs to test.
---

# WordPress Website QC

Perform a structured quality-control audit of the web pages the user gives you
and deliver an Excel/CSV report. Testing is **fetch-based** (no headless
browser): the page HTML and its linked CSS are downloaded and analysed; nothing
on the page is executed.

## Inputs you need
- **One or more URLs** (the pages to QC). Accept them pasted, in a file, or as a
  list. If none are given, ask for them.
- Optional: **tester name** and **date** for the report header (default: today).
- Optional: the **approved design** / client's real contact details — only needed
  to confirm the subjective rows; proceed without them and mark those `Manual`.

## Workflow

### 1. Collect the URLs
Gather every URL. If the user pasted many, write them one per line to a file
(e.g. the scratchpad) and use `--file`. Normalise bare domains to `https://`.

### 2. Run the automated scan
From `scripts/`:
```bash
python qc_scan.py <URL> [<URL> ...] --out results.json
# or
python qc_scan.py --file urls.txt --out results.json
```
This fetches each page and fills every automatable checkpoint with a **Status**
(`Pass` / `Fail` / `Warning` / `Info` / `N/A`), an **Actual Result**, and
**Remarks**. Subjective checkpoints are left as `Manual` with guidance, and the
raw evidence Claude needs (page text, headings, buttons, emails/phones, broken
links, external links) is stored under each result's `raw` key.

Prereqs: Python 3 with `requests`, `beautifulsoup4`, `openpyxl` (already present
in this environment). If `openpyxl` is missing the report falls back to CSV only.

### 3. Judge the subjective rows (Claude, from the fetched content)
Open `results.json`. For each page, use the `raw` evidence — and `WebFetch` on
the URL if you want the rendered reading — to decide the `Manual`/`Info` rows you
*can* judge from content, and update their `status`/`actual`/`remarks` in the
JSON:
- **Row 9 — spelling/grammar/punctuation:** read `raw.page_text`; list any errors
  in Remarks and set `Pass`/`Fail`.
- **Row 13 — labels/CTA/contact details:** sanity-check `raw.emails`, `raw.phones`,
  and `raw.buttons`. If the user supplied the client's real details, compare.
- **Row 8 — headings correct:** scan `raw.headings` for typos/wrong text.
- **Row 23 — button labels match actions:** compare each `raw.buttons[].label`
  with its `href`.
- **Row 58 — URL readable** and **Row 57 — title appropriate:** confirm wording.

Leave genuinely visual/interactive rows (design match, alignment, spacing,
hover/focus, form submission, cross-browser, console errors, contrast, carousels)
as `Manual` — the Remarks already tell the tester exactly what to check live.
Do **not** invent a Pass for something a fetch cannot verify.

Re-save the edited `results.json`.

### 4. Build the report
```bash
python build_report.py results.json --out "QC-Report.xlsx" --qc-by "<name>" --date <YYYY-MM-DD>
```
Produces:
- **QC-Report.xlsx** — a *Summary* sheet (per-URL pass/fail counts) plus **one
  sheet per URL** with colour-coded status cells, using the exact columns
  `Sr. No. | Module | Checkpoint | Status | Actual Result | Remarks`.
- **A .csv per URL** next to it (UTF-8 BOM, imports cleanly into Google Sheets/Excel).

Write the report into the user's working directory unless they say otherwise.

### 5. Report back
Give the user:
- Where the files are (full absolute paths).
- A short per-page summary: counts of Pass / Fail / Warning / Manual, and the
  **top issues** (every `Fail` and notable `Warning`) called out in plain language
  — e.g. "3 broken links, title too long, 4 images under 16px, no meta description".
- Remind them which rows still need a human eye (the `Manual` ones) and why.

## Status vocabulary
| Status | Meaning |
|--------|---------|
| **Pass** | Automatically verified OK. |
| **Fail** | Automatically detected problem — fix needed. |
| **Warning** | Likely issue / outside best-practice threshold — review. |
| **Info** | Detected and reported; needs a human judgement call (e.g. "12 font families"). |
| **Manual** | Cannot be verified by fetch; needs a rendered browser or interaction. |
| **N/A** | Not applicable to this page (e.g. no forms, no video). |

## Notes & honesty
- **External links** that return 403/405/timeout are often bot-blocked, not
  broken — they are flagged `Warning`, not `Fail`. Say so.
- Font-size / responsive checks read the inline and first few linked stylesheets;
  themes using `rem`/`em` or many CSS files may need a visual confirm — the
  Remarks say when the signal is uncertain.
- Never report a checkpoint as tested when it was only fetched. If something was
  skipped or couldn't be judged, keep it `Manual` and say why.

See `references/checklist.md` for every checkpoint and exactly how each is tested.
