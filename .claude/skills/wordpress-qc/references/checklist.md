# QC Checklist — how each checkpoint is tested

`A` = automated by `qc_scan.py` (from fetched HTML/CSS) · `J` = Claude judges from
fetched content · `M` = manual (needs a rendered browser / interaction).

Report columns: **Sr. No. | Module | Checkpoint | Status | Actual Result | Remarks**.

## Page Layout & UI
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 1 | Layout matches approved design | M | Needs the design file; compare visually. |
| 2 | Sections/columns/content aligned | M | Visual at a rendered viewport. |
| 3 | Font family, size, weight, colours consistent | A/J | Extracts distinct `font-family` from inline + linked CSS; lists them (Info). Confirm against design. |
| 4 | Spacing/margins/padding consistent | M | Visual. |
| 5 | Backgrounds/borders/dividers correct | M | Visual. |
| 6 | No overlap/clip/overflow of content | M | Visual at each breakpoint. |
| 7 | No unexpected horizontal scrolling | A/M | Reports viewport meta + oversized fixed widths; confirm visually. |

## Content
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 8 | Headings/subheadings correct | A/J | Lists all h1–h6 text in `raw.headings`; Claude checks wording. |
| 9 | Spelling, grammar, punctuation | J | Claude reads `raw.page_text` and flags errors. |
| 10 | Content complete & not duplicated | A | Detects repeated paragraph blocks. |
| 11 | Text readable / not cut off | M | Visual (CSS clamp/overflow). |
| 12 | No placeholder text | A | Scans for lorem ipsum, "coming soon", "dummy text", etc. |
| 13 | Labels, CTA text, contact details correct | A/J | Extracts emails/phones/buttons; Claude verifies vs client details. |
| 65 | Body/content font size ≥ 16px | A | Parses CSS `font-size`; checks body base and flags sub-16px sizes. |

## Navigation & Links
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 14 | Logo navigates to expected page | A | Finds logo link; checks it points to site root. |
| 15 | Header nav links correct destinations | A | Status-checks all `<header>`/`<nav>` links. |
| 16 | Internal links open correct pages | A | HTTP status of every internal link (2xx/3xx = ok). |
| 17 | External links open expected destinations | A | Status-checks external links (403/405/timeout → Warning, bot-blocked). |
| 18 | No broken links / 404s | A | Status of all links; lists broken ones. |
| 19 | Breadcrumbs work, if present | A | Detects breadcrumb markup/schema. |
| 20 | Browser Back behaves | M | Interactive. |

## Buttons & CTA
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 21 | All buttons clickable | A | Counts button/CTA elements; notes disabled ones. |
| 22 | Each CTA opens correct destination | A/J | Status-checks linked CTA targets; JS-only buttons → manual. |
| 23 | Button labels match actions | J | Claude compares `raw.buttons[].label` with `href`. |
| 24 | Hover/focus/disabled states | M | Interactive. |
| 25 | Repeated clicks no duplicate action | M | Interactive. |

## Images & Icons
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 26 | Images load correctly | A | HTTP status of every `<img>` source. |
| 27 | Images not stretched/distorted | A/M | Reports width/height attrs; distortion needs rendering. |
| 28 | Clickable icons perform action | A | Detects icon-in-link elements; confirm action manually. |
| 29 | Social icons open correct profiles | A | Extracts social links; confirm handles. |
| 30 | Sliders/carousels work | A/M | Detects slider markup; confirm JS behaviour. |
| 31 | Videos/media controls work | A/M | Detects `<video>`/`<iframe>` embeds; confirm controls. |
| 32 | Meaningful alt text present | A | Checks `alt` coverage across images. |

## Forms
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 33 | Fields/labels/placeholders display | A | Counts forms, fields, labels. |
| 34 | Required fields can't submit empty | A | Detects `required` attributes; confirm by submitting. |
| 35 | Valid input accepted | M | Submit a real form. |
| 36 | Invalid email/phone handled | M | Submit a real form. |
| 37 | Validation messages appear | M | Submit a real form. |
| 38 | Success confirmation shows | M | Submit a real form. |
| 39 | Duplicate submissions handled | M | Submit a real form. |
| 40 | Consent/privacy checkbox rules | A | Detects consent/privacy checkboxes. |

## Responsive
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 41 | Desktop layout | M | Visual at ~1280px+. |
| 42 | Tablet layout | A/M | Reports media queries; confirm at ~768px. |
| 43 | Mobile layout | A/M | Reports viewport meta + media queries; confirm at ~375px. |
| 44 | Text/images/buttons stay in viewport | A/M | Flags oversized fixed widths; confirm visually. |
| 45 | Mobile menu opens/closes | A/M | Detects menu toggle; confirm it works. |
| 46 | Usable on touch screens | M | Device/emulator. |

## Browser & Functionality
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 47 | Loads directly by URL | A | HTTP 200 on GET. |
| 48 | Refresh works | A | Stateless GET returns same 200. |
| 49 | Works in supported browsers | M | Test in real browsers. |
| 50 | No relevant console errors | M | Needs DevTools/JS execution. |
| 51 | Loading/interactions responsive | A | Fetch timing + HTML size (render excluded). |
| 52 | Pop-ups/cookie banners/overlays | A/M | Detects cookie/popup markup; confirm behaviour. |

## Footer & Common Elements
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 53 | Footer content correct & consistent | A/J | Extracts footer links/text; confirm wording. |
| 54 | Footer navigation links work | A | Status-checks footer links. |
| 55 | Phone/email links work | A | Detects `tel:`/`mailto:` and formats. |
| 56 | Copyright text/year correct | A | Finds footer year; compares to current year. |

## Basic SEO & Accessibility
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 57 | Page title appropriate | A/J | Reads `<title>`, checks length; Claude confirms wording. |
| 58 | URL correct & readable | A/J | Flags uppercase/underscore/non-pretty permalinks. |
| 59 | Main H1 & heading hierarchy | A | Exactly one H1, no skipped levels. |
| 60 | Keyboard navigation reaches links/buttons | A/M | Reports focusable elements + skip-link; confirm focus/order. |
| 61 | Text/background contrast readable | M | Run a contrast checker on the live page. |

## Page-Specific Checks
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 62 | Page-specific sections/components work | M | Needs intended behaviour + rendering. |
| 63 | Cards/accordions/tabs/filters/pagination | M | JS-driven; confirm interactively. |
| 64 | Section-specific links & CTAs navigate | A | Rolls up link/CTA status for the page. |

## Technical & SEO (added checkpoints)
| Sr | Checkpoint | Type | How it's tested |
|----|------------|------|-----------------|
| 66 | Served over HTTPS with valid cert | A | Scheme + successful TLS fetch. |
| 67 | No mixed content on HTTPS page | A | Flags `http://` asset references. |
| 68 | Meta description present & sized | A | Presence + 50–160 char length. |
| 69 | Canonical URL present & self-referential | A | Reads `<link rel=canonical>`. |
| 70 | Not accidentally noindex/nofollow | A | Reads robots meta. |
| 71 | Open Graph / social tags present | A | Counts `og:`/`twitter:` tags. |
| 72 | Viewport meta present | A | Required for responsiveness. |
| 73 | `<html lang>` set | A | Accessibility/SEO. |
| 74 | Favicon defined | A | `<link rel=icon>`. |
| 75 | No empty/placeholder anchors | A | Flags `href="#"` / `javascript:`. |
| 76 | No duplicate element IDs | A | Breaks anchors/JS/a11y. |
| 77 | Confirm WordPress | A | Generator meta / wp-content / wp-json markers. |

> Add more checkpoints by appending to `CHECKLIST` in `scripts/qc_scan.py` (and a
> `put(...)` for automated ones, or an entry in `MANUAL_GUIDANCE` for manual ones).
