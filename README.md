# Justwords QC tool

An AI-assisted website **quality-control dashboard**. Paste a URL (or add
images), and it runs the full **77-point QC checklist** and layers an AI expert
verdict on top — no setup, no keys to enter.

- **Fetch-based** — the scanned page's HTML and a few stylesheets are downloaded
  and parsed. Nothing on the page is ever executed.
- **No key in the UI** — the AI key and model live on the server (an environment
  variable), so end users just open the page and scan.
- **Clickable status filters** — click *Fail / Warning / Pass / Info / Manual /
  N/A* to show only those checkpoints.

## What it checks

Every checkpoint from the QC checklist:

| Area | Examples |
|------|----------|
| Page Layout & UI | fonts, horizontal scroll |
| Content | headings, spelling/grammar (AI), placeholder text, duplication, ≥16px body |
| Navigation & Links | broken links/404s, header/footer/internal/external, logo, breadcrumbs |
| Buttons & CTA | clickable, destinations resolve, labels match actions (AI) |
| Images & Icons | load, alt text, social icons, sliders, media |
| Forms | fields/labels, required, consent checkboxes |
| Responsive | viewport, media queries, mobile menu, oversized widths |
| Browser & Functionality | load, refresh, timing, cookie/popup markup |
| Footer | links, phone/email, copyright year |
| Basic SEO & Accessibility | title, URL, H1 hierarchy, keyboard focus |
| Technical & SEO | HTTPS, mixed content, meta description, canonical, robots, OG, favicon, duplicate IDs, WordPress detection |

Rows a fetch cannot verify (visual layout, real form submission, cross-browser…)
are marked **Manual** with guidance. The **AI layer** judges the subjective text
rows (headings, spelling/grammar, CTA/contact correctness, title, URL) and writes
an overall verdict with a content score, top issues, and strengths.

**Image QC** measures each image you add (dimensions, file weight, format, aspect
ratio) in the browser, then the AI reviewer assesses fitness for web use —
resolution, page-weight, format suitability and distortion risk.

## Run locally

```bash
pip install -r requirements.txt
# provide your key either way:
export GROQ_API_KEY=gsk_...        # Windows: set GROQ_API_KEY=gsk_...
# or create a (gitignored) groq_key.txt next to app.py containing the key
python app.py
# open http://localhost:5000
```

## Deploy on Render

This repo includes a `render.yaml` blueprint.

1. Push to GitHub.
2. In Render: **New → Blueprint**, point it at the repo. Render runs
   `gunicorn app:app` on the free plan.
3. In the service's **Environment** tab, set `GROQ_API_KEY` to your key (the
   blueprint already declares it with `sync: false`, so Render will prompt for
   it). `QC_MODEL` defaults to `openai/gpt-oss-120b`.

## Project layout

```
app.py            Flask app: routes, scoring, AI merge, server-side key/model
qc_core.py        Fetch-based 77-point scanner
ai_engine.py      AI calls: content verdict + image assessment
static/           Frontend (index.html, style.css, app.js)
render.yaml       Render blueprint
requirements.txt  Python deps
```

## API

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/scan` | `{url}` | 77 checkpoints + AI verdict |
| POST | `/api/scan-image` | `{images[], context?}` | AI image assessment |
