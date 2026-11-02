# QC Dashboard

An AI-assisted website **quality-control dashboard**. Paste a URL (or drop in
design screenshots), and it runs the full **77-point QC checklist** used by the
`wordpress-qc` workflow, then layers a **Groq**-powered expert verdict on top.

- **Fetch-based** — the scanned page's HTML and a few stylesheets are downloaded
  and parsed. Nothing on the page is ever executed.
- **Your Groq API key stays in your browser.** It is typed into the frontend,
  stored only in `localStorage`, and forwarded per request. The server never
  stores it, logs it, or reads it from the environment.

## What it checks

Every checkpoint from `.claude/skills/wordpress-qc/references/checklist.md`:

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

**Image / design QC** sends your screenshot(s) to a Groq **vision** model for a
visual review of layout, alignment, spacing, typography, contrast, overlap,
imagery and CTA visibility.

## Run locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

Then paste your Groq API key (get one at https://console.groq.com/keys),
optionally click **Fetch models** to pick a model, and run a scan.

## Deploy on Render

This repo includes a `render.yaml` blueprint.

1. Push to GitHub (this repo).
2. In Render: **New → Blueprint**, point it at the repo. Render reads
   `render.yaml` and creates a free web service running
   `gunicorn app:app`.
3. No environment variables are required — the Groq key is supplied by each user
   in the browser.

Or deploy manually: **New → Web Service**, Build `pip install -r requirements.txt`,
Start `gunicorn app:app --bind 0.0.0.0:$PORT`.

## Project layout

```
app.py            Flask app: routes, scoring, AI merge
qc_core.py        Fetch-based 77-point scanner (ported from the skill)
groq_judge.py     Groq calls: model list, content verdict, vision QC
static/           Frontend (index.html, style.css, app.js)
render.yaml       Render blueprint
requirements.txt  Python deps
```

## API

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/models` | `{apiKey}` | model ids the key can use |
| POST | `/api/scan` | `{url, apiKey?, model?}` | 77 checkpoints + AI verdict |
| POST | `/api/scan-image` | `{images[], apiKey, model?, context?}` | visual QC verdict |

The Groq key is optional for `/api/scan` (you still get the full automated audit);
it is required for AI verdicts and all image QC.
