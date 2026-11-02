#!/usr/bin/env python3
"""
qc_core.py -- fetch-based WordPress/website QC scanner (importable).

Ported from the wordpress-qc skill's qc_scan.py. Fetches a URL once, parses the
HTML + a few linked stylesheets, and fills every automatable checkpoint from the
77-point QC checklist with a Status / Actual Result / Remarks, plus the raw
evidence an LLM needs to judge the subjective rows.

Nothing from the fetched page is executed; HTML is parsed, never run.
"""

import concurrent.futures as cf
import datetime as dt
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 QC-Scanner")
TIMEOUT = 15
LINK_CAP = 150
CSS_CAP = 8
CURRENT_YEAR = dt.date.today().year

PASS, FAIL, WARN, MANUAL, INFO, NA = "Pass", "Fail", "Warning", "Manual", "Info", "N/A"

# (sr, module, checkpoint, auto|manual)
CHECKLIST = [
    (1,  "Page Layout & UI", "Verify page layout matches the approved design", "manual"),
    (2,  "Page Layout & UI", "Verify sections, columns, and content are properly aligned", "manual"),
    (3,  "Page Layout & UI", "Verify font family, size, weight, and colors are consistent", "auto"),
    (4,  "Page Layout & UI", "Verify spacing, margins, and padding are consistent", "manual"),
    (5,  "Page Layout & UI", "Verify backgrounds, borders, and divider lines display correctly", "manual"),
    (6,  "Page Layout & UI", "Verify no content overlaps, clips, or appears outside its container", "manual"),
    (7,  "Page Layout & UI", "Verify no unexpected horizontal scrolling", "auto"),
    (8,  "Content", "Verify headings and subheadings are correct", "auto"),
    (9,  "Content", "Check spelling, grammar, and punctuation", "manual"),
    (10, "Content", "Verify content is complete and not duplicated", "auto"),
    (11, "Content", "Verify text is readable and not cut off", "manual"),
    (12, "Content", "Verify no placeholder text remains", "auto"),
    (13, "Content", "Verify labels, CTA text, and contact details are correct", "auto"),
    (65, "Content", "Verify the body/content font size is at least 16px", "auto"),
    (14, "Navigation & Links", "Verify logo navigates to the expected page", "auto"),
    (15, "Navigation & Links", "Verify header navigation links open the correct destinations", "auto"),
    (16, "Navigation & Links", "Verify internal links open the correct pages", "auto"),
    (17, "Navigation & Links", "Verify external links open the expected destinations", "auto"),
    (18, "Navigation & Links", "Verify no broken links or unexpected 404 pages", "auto"),
    (19, "Navigation & Links", "Verify breadcrumbs work correctly, if present", "auto"),
    (20, "Navigation & Links", "Verify browser Back navigation behaves as expected", "manual"),
    (21, "Buttons & CTA", "Verify all buttons are clickable", "auto"),
    (22, "Buttons & CTA", "Verify each CTA performs the expected action or opens the correct destination", "auto"),
    (23, "Buttons & CTA", "Verify button labels match their actions", "manual"),
    (24, "Buttons & CTA", "Verify hover, focus, and disabled states, where applicable", "manual"),
    (25, "Buttons & CTA", "Verify repeated clicks do not trigger unintended duplicate actions", "manual"),
    (26, "Images & Icons", "Verify images load correctly", "auto"),
    (27, "Images & Icons", "Verify images are not stretched, distorted, or cropped unexpectedly", "auto"),
    (28, "Images & Icons", "Verify clickable icons perform the expected action", "auto"),
    (29, "Images & Icons", "Verify social media icons open the correct profiles", "auto"),
    (30, "Images & Icons", "Verify sliders and carousels work correctly, if present", "auto"),
    (31, "Images & Icons", "Verify videos and other media controls work, if present", "auto"),
    (32, "Images & Icons", "Verify meaningful alt text is present where required", "auto"),
    (33, "Forms", "Verify fields, labels, and placeholders display correctly", "auto"),
    (34, "Forms", "Verify required fields cannot be submitted empty", "auto"),
    (35, "Forms", "Verify valid input is accepted", "manual"),
    (36, "Forms", "Verify invalid email and phone formats are handled correctly", "manual"),
    (37, "Forms", "Verify appropriate validation messages appear", "manual"),
    (38, "Forms", "Verify successful submission shows the expected confirmation", "manual"),
    (39, "Forms", "Verify duplicate submissions are handled appropriately", "manual"),
    (40, "Forms", "Verify consent and privacy checkbox rules, if present", "auto"),
    (41, "Responsive", "Verify layout at desktop screen sizes", "manual"),
    (42, "Responsive", "Verify layout at tablet screen sizes", "auto"),
    (43, "Responsive", "Verify layout at mobile screen sizes", "auto"),
    (44, "Responsive", "Verify text, images, and buttons stay within the viewport", "auto"),
    (45, "Responsive", "Verify mobile menu opens and closes correctly, if present", "auto"),
    (46, "Responsive", "Verify buttons and links are usable on touch screens", "manual"),
    (47, "Browser & Functionality", "Verify page loads correctly when opened directly by URL", "auto"),
    (48, "Browser & Functionality", "Verify page refresh works as expected", "auto"),
    (49, "Browser & Functionality", "Verify page works in supported browsers", "manual"),
    (50, "Browser & Functionality", "Check for relevant console errors, if DevTools access is available", "manual"),
    (51, "Browser & Functionality", "Verify loading and interactions are reasonably responsive", "auto"),
    (52, "Browser & Functionality", "Verify pop-ups, cookie banners, and overlays behave as expected, if present", "auto"),
    (53, "Footer & Common Elements", "Verify footer content is correct and consistent", "auto"),
    (54, "Footer & Common Elements", "Verify footer navigation links work", "auto"),
    (55, "Footer & Common Elements", "Verify phone and email links work, if present", "auto"),
    (56, "Footer & Common Elements", "Verify copyright text/year is correct", "auto"),
    (57, "Basic SEO & Accessibility", "Verify page title is appropriate", "auto"),
    (58, "Basic SEO & Accessibility", "Verify URL is correct and readable", "auto"),
    (59, "Basic SEO & Accessibility", "Verify the main H1 and heading hierarchy are appropriate", "auto"),
    (60, "Basic SEO & Accessibility", "Verify keyboard navigation reaches links and buttons", "auto"),
    (61, "Basic SEO & Accessibility", "Verify text/background contrast is readable", "manual"),
    (62, "Page-Specific Checks", "Verify all page-specific sections and components work as expected", "manual"),
    (63, "Page-Specific Checks", "Verify cards, accordions, tabs, filters, or pagination, if present", "manual"),
    (64, "Page-Specific Checks", "Verify section-specific links and CTAs navigate correctly", "auto"),
    (66, "Technical & SEO", "Verify the page is served over HTTPS with a valid certificate", "auto"),
    (67, "Technical & SEO", "Verify there is no mixed content (http assets on an https page)", "auto"),
    (68, "Technical & SEO", "Verify a meta description is present and a sensible length", "auto"),
    (69, "Technical & SEO", "Verify a canonical URL is present and self-referential", "auto"),
    (70, "Technical & SEO", "Verify the page is not accidentally set to noindex/nofollow", "auto"),
    (71, "Technical & SEO", "Verify Open Graph / social share tags are present", "auto"),
    (72, "Technical & SEO", "Verify a viewport meta tag is present for responsiveness", "auto"),
    (73, "Technical & SEO", "Verify the <html> lang attribute is set", "auto"),
    (74, "Technical & SEO", "Verify a favicon is defined", "auto"),
    (75, "Technical & SEO", "Verify no empty/placeholder anchors (href='#', 'javascript:void')", "auto"),
    (76, "Technical & SEO", "Verify no duplicate element IDs on the page", "auto"),
    (77, "Technical & SEO", "Confirm the site is built on WordPress (generator/paths)", "auto"),
]

MANUAL_GUIDANCE = {
    1: "No approved design supplied to the scanner. Compare the rendered page against the Figma/PSD/approved mockup.",
    2: "Visual alignment needs a rendered viewport. Open the page and eyeball section/column/grid alignment.",
    4: "Spacing/margins/padding consistency needs visual inspection across sections.",
    5: "Backgrounds, borders, and dividers need visual confirmation.",
    6: "Overlap/clipping/overflow of content needs a rendered browser at each breakpoint.",
    9: "Read the extracted page text (raw.page_text) and flag spelling, grammar, and punctuation errors.",
    11: "Text truncation/cut-off needs a rendered viewport; check CSS line-clamp / overflow:hidden areas.",
    20: "Open two pages, click through, then press Back and confirm the previous page restores correctly.",
    23: "Compare each button label (raw.buttons) against what it actually does/links to.",
    24: "Hover/focus/disabled states need a rendered browser with pointer and keyboard.",
    25: "Submit/CTA double-click behaviour needs interaction; confirm no duplicate orders/form posts.",
    35: "Valid-input acceptance needs real form submission.",
    36: "Invalid email/phone handling needs real form submission.",
    37: "Validation-message display needs real form submission.",
    38: "Success confirmation needs real form submission.",
    39: "Duplicate-submission handling needs real form submission.",
    41: "Desktop layout needs a rendered viewport; confirm the ~1280px+ layout looks correct.",
    46: "Touch target size/usability needs a real device or device emulation.",
    49: "Cross-browser rendering needs the actual browsers (Chrome, Firefox, Safari, Edge).",
    50: "Console errors need DevTools/JS execution, which a fetch cannot capture. Open DevTools and check.",
    61: "Colour contrast needs rendered colours; run an a11y contrast checker on the live page.",
    62: "Page-specific components need a rendered browser and knowledge of the intended behaviour.",
    63: "Cards/accordions/tabs/filters/pagination are JS-driven; confirm interactively.",
}

# Checkpoints an LLM can meaningfully judge from the fetched text evidence.
AI_JUDGEABLE = [8, 9, 10, 13, 23, 57, 58]


def checklist_meta():
    return [{"sr": s, "module": m, "checkpoint": c, "mode": mode} for s, m, c, mode in CHECKLIST]


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


def status_of(session, url, method="head"):
    try:
        if method == "head":
            r = session.head(url, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code in (403, 405, 400) or r.status_code >= 500:
                r = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
                r.close()
        else:
            r = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
            r.close()
        return r.status_code, str(r.url)
    except requests.RequestException as e:
        return None, type(e).__name__


def check_links(session, links):
    uniq = list(dict.fromkeys(links))[:LINK_CAP]
    out = {}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(status_of, session, u): u for u in uniq}
        for fut in cf.as_completed(futs):
            out[futs[fut]] = fut.result()
    return out


def collect_css_text(session, soup, base):
    css = "\n".join(st.get_text() for st in soup.find_all("style"))
    hrefs = []
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if href:
            hrefs.append(urljoin(base, href))
    for href in hrefs[:CSS_CAP]:
        try:
            r = session.get(href, timeout=TIMEOUT)
            if r.ok and "css" in r.headers.get("content-type", "") or href.endswith(".css"):
                css += "\n" + r.text[:400000]
        except requests.RequestException:
            pass
    return css


def scan_url(url):
    session = new_session()
    row = {}
    raw = {}

    def put(sr, status, actual="", remarks=""):
        row[sr] = {"status": status, "actual": str(actual), "remarks": str(remarks)}

    t0 = time.time()
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        err = f"{type(e).__name__}: {e}"
        for sr, *_ in CHECKLIST:
            put(sr, FAIL if sr in (47, 48) else MANUAL, err, "Page could not be fetched.")
        return {"url": url, "error": err, "rows": row, "raw": raw}
    load_ms = int((time.time() - t0) * 1000)
    final_url = str(resp.url)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    parsed = urlparse(final_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    page_size_kb = round(len(resp.content) / 1024, 1)

    if resp.status_code == 200:
        put(47, PASS, f"HTTP {resp.status_code}", f"Loaded directly by URL in {load_ms} ms.")
        put(48, PASS, f"HTTP {resp.status_code}", "Stateless GET; refresh returns the same 200 response.")
    else:
        put(47, FAIL, f"HTTP {resp.status_code}", "Page did not return 200 OK.")
        put(48, WARN, f"HTTP {resp.status_code}", "Non-200 response on load.")
    load_status = PASS if load_ms < 2500 else (WARN if load_ms < 5000 else FAIL)
    put(51, load_status, f"{load_ms} ms, {page_size_kb} KB HTML",
        "Fetch-level timing only (excludes JS/render). <2.5s good, 2.5-5s review, >5s slow.")

    title = (soup.title.get_text(strip=True) if soup.title else "")
    raw["title"] = title
    if not title:
        put(57, FAIL, "(empty)", "No <title> tag.")
    elif len(title) > 65:
        put(57, WARN, title, f"Title is {len(title)} chars (may truncate in SERP > ~60).")
    elif len(title) < 10:
        put(57, WARN, title, f"Title is short ({len(title)} chars); confirm it is descriptive.")
    else:
        put(57, PASS, title, f"{len(title)} chars.")

    path = parsed.path
    url_issues = []
    if re.search(r"[A-Z]", path):
        url_issues.append("uppercase letters")
    if "_" in path:
        url_issues.append("underscores (prefer hyphens)")
    if re.search(r"[?&](p|page_id|cat)=", parsed.query):
        url_issues.append("non-pretty permalink (?p= / ?page_id=)")
    if "%20" in path or " " in path:
        url_issues.append("spaces")
    put(58, WARN if url_issues else PASS, final_url,
        ("Issues: " + ", ".join(url_issues)) if url_issues else "Clean, readable URL.")

    md = soup.find("meta", attrs={"name": "description"})
    md_c = md.get("content", "").strip() if md else ""
    raw["meta_description"] = md_c
    if not md_c:
        put(68, FAIL, "(missing)", "No meta description.")
    elif not (50 <= len(md_c) <= 160):
        put(68, WARN, md_c[:120], f"Length {len(md_c)} chars (recommended 50-160).")
    else:
        put(68, PASS, f"{len(md_c)} chars", md_c[:120])

    can = soup.find("link", rel=lambda v: v and "canonical" in v)
    can_h = urljoin(final_url, can.get("href")) if can and can.get("href") else ""
    if not can_h:
        put(69, WARN, "(missing)", "No canonical link. WordPress/Yoast usually adds one.")
    elif can_h.rstrip("/") == final_url.rstrip("/"):
        put(69, PASS, can_h, "Self-referential canonical.")
    else:
        put(69, INFO, can_h, "Canonical points elsewhere; confirm this is intended.")

    robots = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    robots_c = robots.get("content", "").lower() if robots else ""
    if "noindex" in robots_c or "nofollow" in robots_c:
        put(70, FAIL, robots_c, "Page is set to noindex/nofollow - remove before go-live unless intended.")
    else:
        put(70, PASS, robots_c or "(default index,follow)", "Indexable.")

    og = soup.find_all("meta", property=re.compile("^og:"))
    tw = soup.find_all("meta", attrs={"name": re.compile("^twitter:")})
    put(71, PASS if og else WARN, f"{len(og)} OG tags, {len(tw)} Twitter tags",
        "" if og else "No Open Graph tags; social shares may look poor.")

    vp = soup.find("meta", attrs={"name": "viewport"})
    put(72, PASS if vp else FAIL, vp.get("content", "") if vp else "(missing)",
        "" if vp else "No viewport meta - page will not be mobile-responsive.")

    lang = soup.find("html").get("lang") if soup.find("html") else None
    put(73, PASS if lang else WARN, lang or "(missing)", "" if lang else "Set <html lang> for accessibility/SEO.")

    icon = soup.find("link", rel=lambda v: v and "icon" in v)
    put(74, PASS if icon else WARN, (icon.get("href") if icon else "(missing)"),
        "" if icon else "No favicon declared.")

    if parsed.scheme == "https":
        put(66, PASS, final_url, "Served over HTTPS (reached without SSL error).")
        http_assets = re.findall(r'(?:src|href)=["\']http://[^"\']+', html, flags=re.I)
        http_assets = [a for a in http_assets if "http://www.w3.org" not in a and "http://schema.org" not in a]
        if http_assets:
            put(67, FAIL, f"{len(http_assets)} http:// asset reference(s)",
                "Mixed content on an HTTPS page; examples: " + "; ".join(a[:80] for a in http_assets[:3]))
        else:
            put(67, PASS, "none", "No insecure http:// asset references found.")
    else:
        put(66, FAIL, final_url, "Not served over HTTPS.")
        put(67, NA, "", "Page is not HTTPS.")

    heads = [(int(h.name[1]), h.get_text(" ", strip=True)) for h in soup.find_all(re.compile("^h[1-6]$"))]
    raw["headings"] = [{"level": l, "text": t} for l, t in heads]
    h1s = [t for l, t in heads if l == 1]
    put(8, PASS if heads else WARN, f"{len(heads)} headings",
        "Review heading/subheading text in raw.headings for correctness." if heads else "No headings found.")
    hier_issues = []
    if len(h1s) == 0:
        hier_issues.append("no H1")
    elif len(h1s) > 1:
        hier_issues.append(f"{len(h1s)} H1s (expected 1)")
    prev = 0
    for l, _ in heads:
        if prev and l > prev + 1:
            hier_issues.append(f"jump H{prev}->H{l}")
        prev = l
    put(59, FAIL if ("no H1" in str(hier_issues)) else (WARN if hier_issues else PASS),
        f"H1={h1s or '(none)'}", "; ".join(hier_issues) if hier_issues else "Single H1, no skipped levels.")

    page_text = soup.get_text(" ", strip=True)
    raw["page_text"] = page_text[:6000]
    placeholders = []
    for pat in [r"lorem ipsum", r"dolor sit amet", r"placeholder text", r"dummy text",
                r"insert (?:text|content) here", r"your text here", r"coming soon",
                r"sample text", r"text goes here", r"lipsum"]:
        if re.search(pat, page_text, re.I):
            placeholders.append(pat.replace(r"(?:text|content)", "text/content"))
    put(12, FAIL if placeholders else PASS, "; ".join(placeholders) if placeholders else "none found",
        "Placeholder phrases detected - review." if placeholders else "No common placeholder phrases in visible text.")

    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
    dupes = len(paras) - len(set(paras))
    put(10, WARN if dupes else PASS, f"{len(paras)} paragraphs, {dupes} duplicate",
        "Duplicate paragraph blocks detected; confirm intentional." if dupes else "No duplicated paragraph blocks.")

    css = collect_css_text(session, soup, final_url)
    families = set(re.findall(r"font-family\s*:\s*([^;{}]+)", css, re.I))
    fam_clean = sorted({f.strip().split(",")[0].strip(" '\"") for f in families if f.strip()})[:12]
    put(3, INFO, f"{len(fam_clean)} base families: {', '.join(fam_clean) if fam_clean else 'n/a'}",
        "Font family/size/weight/colour consistency is partly visual - confirm against design.")
    px_sizes = [float(x) for x in re.findall(r"font-size\s*:\s*([\d.]+)px", css, re.I)]
    body_match = re.search(r"body\s*\{[^}]*font-size\s*:\s*([\d.]+)px", css, re.I)
    small = sorted({s for s in px_sizes if s < 16})
    if body_match:
        body_px = float(body_match.group(1))
        put(65, PASS if body_px >= 16 else FAIL, f"body font-size: {body_px}px",
            "Body base >=16px." if body_px >= 16 else "Body base font-size below 16px.")
    elif px_sizes:
        put(65, WARN if small else PASS,
            f"no explicit body size; {len(small)} declared size(s) <16px" if small else "no sizes <16px in CSS",
            ("Small sizes found: " + ", ".join(f"{s}px" for s in small)) if small else
            "No sub-16px font-size declarations found in scanned CSS.")
    else:
        put(65, MANUAL, "no px font-size in scanned CSS",
            "Theme may set sizes via rem/em or external CSS not scanned; confirm computed body size is >=16px.")
    put(7, MANUAL, f"viewport meta: {'yes' if vp else 'no'}",
        "Horizontal scroll needs a rendered viewport; most common cause is a fixed-width element wider than the screen.")

    anchors = soup.find_all("a", href=True)
    internal, external, tel, mailto, empty_anchors = [], [], [], [], 0
    for a in anchors:
        href = a.get("href", "").strip()
        if not href or href == "#" or href.lower().startswith("javascript:"):
            empty_anchors += 1
            continue
        if href.startswith("tel:"):
            tel.append(href); continue
        if href.startswith("mailto:"):
            mailto.append(href); continue
        absu = urljoin(final_url, href.split("#")[0])
        if not absu.startswith("http"):
            continue
        (internal if urlparse(absu).netloc == parsed.netloc else external).append(absu)

    all_links = internal + external
    link_status = check_links(session, all_links)
    broken = {u: v for u, v in link_status.items() if (v[0] is None or v[0] >= 400)}
    raw["broken_links"] = [{"url": u, "status": (v[0] if v[0] else v[1])} for u, v in broken.items()]
    raw["external_links"] = sorted(set(external))[:60]

    put(18, FAIL if broken else PASS,
        f"{len(link_status)} links checked, {len(broken)} broken",
        ("; ".join(f"{u} -> {v[0] or v[1]}" for u, v in list(broken.items())[:6])) if broken else "No broken links / 404s detected.")
    int_broken = [u for u in internal if u in broken]
    put(16, FAIL if int_broken else PASS, f"{len(set(internal))} internal links",
        ("Broken internal: " + "; ".join(int_broken[:5])) if int_broken else "Internal links resolve (2xx/3xx).")
    ext_broken = [u for u in external if u in broken]
    put(17, WARN if ext_broken else PASS, f"{len(set(external))} external links",
        ("Unreachable external (verify manually, some block bots): " + "; ".join(ext_broken[:5])) if ext_broken
        else "External links reachable; confirm destinations are the intended ones.")
    put(75, WARN if empty_anchors else PASS, f"{empty_anchors} empty/js anchors",
        "Links with href='#' or javascript: - fine if JS-driven, otherwise dead links." if empty_anchors
        else "No empty placeholder anchors.")

    navhost = soup.find("header") or soup.find("nav")
    nav_links = []
    if navhost:
        for a in navhost.find_all("a", href=True):
            absu = urljoin(final_url, a["href"].split("#")[0])
            if absu.startswith("http"):
                nav_links.append(absu)
    nav_broken = [u for u in nav_links if u in broken]
    put(15, FAIL if nav_broken else (PASS if nav_links else MANUAL),
        f"{len(set(nav_links))} header/nav links",
        ("Broken nav: " + "; ".join(nav_broken[:5])) if nav_broken else
        ("Header/nav links resolve." if nav_links else "No <header>/<nav> links detected; check menu manually."))

    logo_href = None
    for sel in soup.select("a.logo, a.site-logo, .logo a, .site-branding a, header a[rel='home'], .navbar-brand"):
        if sel.get("href"):
            logo_href = urljoin(final_url, sel["href"]); break
    if not logo_href and navhost:
        first_img_link = navhost.find("a", href=True)
        if first_img_link and first_img_link.find("img"):
            logo_href = urljoin(final_url, first_img_link["href"])
    if logo_href:
        is_home = urlparse(logo_href).path.rstrip("/") in ("", urlparse(origin).path.rstrip("/"))
        put(14, PASS if is_home else WARN, logo_href,
            "Logo links to home." if is_home else "Logo does not point to the site root - confirm intended.")
    else:
        put(14, MANUAL, "logo link not auto-detected", "Confirm the logo links to the homepage.")

    bc = soup.select_one(".breadcrumb, .breadcrumbs, [aria-label*='readcrumb'], nav.rank-math-breadcrumb, .yoast-breadcrumb")
    bc_json = 'BreadcrumbList' in html
    put(19, PASS if (bc or bc_json) else NA,
        "breadcrumb markup present" if (bc or bc_json) else "none",
        "Breadcrumbs found; confirm each crumb links correctly." if (bc or bc_json) else "No breadcrumbs present on this page.")

    footer = soup.find("footer")
    if footer:
        f_links = [urljoin(final_url, a["href"].split("#")[0]) for a in footer.find_all("a", href=True)
                   if a["href"].startswith(("http", "/"))]
        f_broken = [u for u in f_links if u in broken]
        put(53, INFO, f"{len(f_links)} footer links; text len {len(footer.get_text(strip=True))}",
            "Confirm footer text (address, legal, nav) is correct and consistent across pages.")
        put(54, FAIL if f_broken else PASS, f"{len(set(f_links))} footer links",
            ("Broken: " + "; ".join(f_broken[:5])) if f_broken else "Footer links resolve.")
    else:
        put(53, MANUAL, "no <footer> element", "Confirm footer content manually.")
        put(54, MANUAL, "no <footer> element", "Confirm footer links manually.")

    put(55, PASS if (tel or mailto) else NA,
        f"{len(tel)} tel:, {len(mailto)} mailto:",
        ("tel/mailto present: " + "; ".join((tel + mailto)[:4])) if (tel or mailto) else "No tel:/mailto: links on this page.")

    foot_txt = footer.get_text(" ", strip=True) if footer else page_text[-1500:]
    years = re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", foot_txt, re.I)
    if not years:
        years = re.findall(r"\b(20\d{2})\b", foot_txt)
    if years:
        y = max(int(x) for x in years)
        put(56, PASS if y >= CURRENT_YEAR else WARN, f"year: {y}",
            "Current." if y >= CURRENT_YEAR else f"Footer year {y} is behind the current year {CURRENT_YEAR}.")
    else:
        put(56, MANUAL, "no year found in footer", "Confirm copyright text/year manually.")

    imgs = soup.find_all("img")
    img_srcs = []
    for im in imgs:
        s = im.get("src") or im.get("data-src") or ""
        if s and not s.startswith("data:"):
            img_srcs.append(urljoin(final_url, s))
    img_status = check_links(session, img_srcs)
    img_broken = {u: v for u, v in img_status.items() if (v[0] is None or v[0] >= 400)}
    put(26, FAIL if img_broken else PASS, f"{len(imgs)} <img>, {len(img_broken)} broken",
        ("Broken images: " + "; ".join(list(img_broken)[:4])) if img_broken else "All checked image sources load.")
    no_alt = [(im.get("src") or "")[:80] for im in imgs if im.get("alt") is None or im.get("alt", "").strip() == ""]
    put(32, WARN if no_alt else PASS, f"{len(imgs)-len(no_alt)}/{len(imgs)} have alt text",
        (f"{len(no_alt)} image(s) missing alt (ok only if purely decorative).") if no_alt else "All images have alt text.")
    put(27, MANUAL, f"{len([i for i in imgs if i.get('width') and i.get('height')])}/{len(imgs)} have width+height attrs",
        "Stretch/distortion needs rendering. Images with explicit width+height are less likely to shift; confirm aspect ratios visually.")
    icon_links = soup.select("a svg, a i[class*='icon'], a i[class*='fa'], a .icon")
    put(28, INFO if icon_links else NA, f"{len(icon_links)} icon-in-link element(s)",
        "Confirm each clickable icon triggers its intended action/destination." if icon_links else "No obvious clickable icons.")
    social = soup.select("a[href*='facebook'], a[href*='instagram'], a[href*='twitter'], a[href*='linkedin'], a[href*='youtube'], a[href*='x.com'], a[href*='tiktok']")
    put(29, INFO if social else NA, f"{len(social)} social link(s)",
        "Confirm each social icon opens the correct official profile." if social else "No social links detected.")
    slider = soup.select_one("[class*='swiper'], [class*='slick'], [class*='carousel'], [class*='slider'], .owl-carousel, [class*='glide']")
    put(30, INFO if slider else NA, "slider/carousel markup present" if slider else "none",
        "Carousel/slider is JS-driven - confirm arrows, dots, autoplay, and swipe work." if slider else "No slider/carousel detected.")
    media = soup.find_all(["video", "audio"]) + soup.find_all("iframe", src=re.compile(r"youtube|vimeo|wistia|dailymotion", re.I))
    put(31, INFO if media else NA, f"{len(media)} media embed(s)" if media else "none",
        "Confirm play/pause/volume/fullscreen controls work." if media else "No video/audio embeds on this page.")
    raw["images_total"] = len(imgs)

    buttons = soup.find_all("button") + soup.select("a.button, a.btn, a.wp-block-button__link, .elementor-button, input[type='submit']")
    btn_info = []
    for b in buttons[:40]:
        label = b.get_text(" ", strip=True) or b.get("value") or b.get("aria-label") or ""
        href = b.get("href")
        btn_info.append({"label": label, "href": urljoin(final_url, href) if href else None})
    raw["buttons"] = btn_info
    disabled = [b for b in buttons if b.has_attr("disabled")]
    put(21, PASS if buttons else NA, f"{len(buttons)} button/CTA element(s), {len(disabled)} disabled",
        "Buttons present; disabled ones should look disabled." if buttons else "No button-like elements detected.")
    cta_broken = [b["href"] for b in btn_info if b["href"] and b["href"] in broken]
    put(22, FAIL if cta_broken else (PASS if any(b["href"] for b in btn_info) else MANUAL),
        f"{sum(1 for b in btn_info if b['href'])} linked CTAs",
        ("Broken CTA target(s): " + "; ".join(cta_broken[:4])) if cta_broken else
        "Linked CTA destinations resolve; confirm each goes to the intended page. JS-only buttons need manual testing.")
    put(64, PASS if not (cta_broken or int_broken) else WARN,
        "section links/CTAs",
        "Section links & CTAs resolve." if not (cta_broken or int_broken) else "Some section links/CTAs are broken - see rows 16/22.")

    forms = soup.find_all("form")
    fields = soup.find_all(["input", "textarea", "select"])
    labels = soup.find_all("label")
    required = [f for f in fields if f.has_attr("required") or f.get("aria-required") == "true"]
    consent = soup.select("input[type='checkbox'][name*='consent'], input[type='checkbox'][name*='privacy'], input[type='checkbox'][name*='gdpr'], input[type='checkbox'][name*='agree']")
    typed = {f.get("type") for f in fields if f.name == "input"}
    raw["forms"] = {"forms": len(forms), "fields": len(fields), "labels": len(labels),
                    "required": len(required), "types": sorted(t for t in typed if t)}
    if forms:
        put(33, PASS if labels else WARN, f"{len(forms)} form(s), {len(fields)} fields, {len(labels)} labels",
            "Fields present; confirm every field has a visible label/placeholder." if labels else "Fields present but few/no <label>s.")
        put(34, PASS if required else WARN, f"{len(required)} required field(s)",
            "Required attributes present; confirm empty submit is blocked." if required else "No required fields marked - confirm validation.")
        put(40, PASS if consent else NA, f"{len(consent)} consent/privacy checkbox(es)",
            "Consent checkbox present; confirm it is enforced." if consent else "No consent checkbox detected on this page.")
    else:
        put(33, NA, "no forms", "No form on this page.")
        put(34, NA, "no forms", "No form on this page.")
        put(40, NA, "no forms", "No form on this page.")

    media_q = len(re.findall(r"@media[^{]*\(", css))
    put(42, INFO if media_q else WARN, f"{media_q} @media query block(s) in scanned CSS",
        "Media queries present - tablet layout likely handled; still confirm visually at ~768px." if media_q
        else "No media queries found in scanned CSS; responsive behaviour uncertain.")
    put(43, INFO if (media_q and vp) else WARN, f"viewport meta: {'yes' if vp else 'no'}, {media_q} media queries",
        "Mobile prerequisites present; confirm the ~375px layout visually." if (media_q and vp)
        else "Missing viewport meta and/or media queries - mobile layout at risk.")
    fixed_wide = re.findall(r"width\s*:\s*(\d{4,})px", css)
    put(44, WARN if fixed_wide else INFO, f"{len(fixed_wide)} element(s) with width >=1000px",
        "Large fixed widths can overflow small screens; confirm content stays in the viewport." if fixed_wide
        else "No oversized fixed widths flagged; confirm visually.")
    mobile_toggle = soup.select_one(".menu-toggle, .hamburger, [class*='mobile-menu'], button[aria-label*='menu'], .navbar-toggler, [class*='menu-icon']")
    put(45, PASS if mobile_toggle else WARN, "mobile menu toggle present" if mobile_toggle else "no toggle detected",
        "Mobile menu toggle found; confirm it opens/closes." if mobile_toggle else "No mobile menu toggle detected; confirm the nav collapses on mobile.")

    cookie = re.search(r"cookie|consent|gdpr|cookieyes|borlabs|cookie-?law|cookie-?notice", html, re.I)
    popup = soup.select_one("[class*='popup'], [class*='modal'], [id*='popup'], [class*='newsletter']")
    put(52, INFO if (cookie or popup) else NA,
        f"cookie/consent: {'yes' if cookie else 'no'}, popup/modal markup: {'yes' if popup else 'no'}",
        "Confirm banners/overlays appear, dismiss correctly, and don't block content." if (cookie or popup)
        else "No cookie banner / popup markup detected.")

    skip = soup.select_one("a[href='#content'], a[href^='#main'], .skip-link")
    put(60, INFO, f"{len(anchors)} links, {len(buttons)} buttons, skip-link: {'yes' if skip else 'no'}",
        "Links/buttons are natively focusable. Confirm visible focus outlines and logical tab order in a browser." +
        ("" if skip else " No skip-to-content link found."))

    phones = re.findall(r"(?:\+?\d[\d\s().-]{7,}\d)", page_text)
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", html)
    raw["phones"] = sorted(set(phones))[:10]
    raw["emails"] = sorted(set(emails))[:10]
    put(13, INFO, f"{len(set(emails))} email(s), {len(set(phones))} phone-like string(s)",
        "Verify CTA text, labels, phone numbers and email addresses match the client's real details (raw.phones / raw.emails).")

    gen = soup.find("meta", attrs={"name": "generator"})
    gen_c = gen.get("content", "") if gen else ""
    is_wp = ("wordpress" in gen_c.lower() or "wp-content" in html or "wp-includes" in html or "/wp-json" in html)
    put(77, PASS if is_wp else INFO, gen_c or ("wp-content/wp-includes paths found" if is_wp else "no WP markers"),
        "Confirmed WordPress." if is_wp else "WordPress markers not detected (could be headless/obfuscated).")
    raw["wordpress"] = is_wp

    ids = [e.get("id") for e in soup.find_all(id=True)]
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    put(76, WARN if dup_ids else PASS, f"{len(dup_ids)} duplicate id(s)",
        ("Duplicate IDs break anchors/JS/a11y: " + ", ".join(dup_ids[:8])) if dup_ids else "All element IDs unique.")

    for sr, module, checkpoint, mode in CHECKLIST:
        if sr not in row:
            put(sr, MANUAL, "", MANUAL_GUIDANCE.get(sr, "Requires visual/interactive testing in a rendered browser."))

    return {"url": url, "final_url": final_url, "status_code": resp.status_code,
            "load_ms": load_ms, "page_kb": page_size_kb, "wordpress": is_wp,
            "rows": row, "raw": raw}
