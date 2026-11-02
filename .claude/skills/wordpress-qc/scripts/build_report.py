#!/usr/bin/env python3
"""
build_report.py  --  Turn qc_scan results.json into the QC report.

Produces:
  * an Excel workbook (.xlsx): a Summary sheet + one sheet per URL, using the
    QC columns  Sr. No. | Module | Checkpoint | Status | Actual Result | Remarks
  * a .csv per URL (same columns) alongside the workbook, for Google Sheets.

Usage:
    python build_report.py results.json --out QC-Report.xlsx
    python build_report.py results.json --out QC-Report.xlsx --qc-by "Name" --date 2026-10-28
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
from urllib.parse import urlparse

COLUMNS = ["Sr. No.", "Module", "Checkpoint", "Status", "Actual Result", "Remarks"]

STATUS_FILL = {   # status -> (font hex, fill hex)
    "Pass":    ("006100", "C6EFCE"),
    "Fail":    ("9C0006", "FFC7CE"),
    "Warning": ("9C6500", "FFEB9C"),
    "Manual":  ("3F3F76", "DDEBF7"),
    "Info":    ("1F4E78", "E2EFDA"),
    "N/A":     ("808080", "F2F2F2"),
}


def rows_for(result, checklist):
    """Build ordered report rows for one page result."""
    rowmap = result.get("rows", {})
    # keys may be str (from json) or int
    def get(sr):
        return rowmap.get(str(sr)) or rowmap.get(sr) or {}
    out = []
    for item in checklist:
        sr = item["sr"]
        r = get(sr)
        out.append([sr, item["module"], item["checkpoint"],
                    r.get("status", "Not Tested"),
                    r.get("actual", ""), r.get("remarks", "")])
    return out


def safe_sheet_name(url, used):
    host = urlparse(url).netloc or url
    path = urlparse(url).path.strip("/").replace("/", "-")
    name = (host + ("-" + path if path else "")) or "page"
    name = re.sub(r"[\[\]\:\*\?\/\\]", "-", name)[:28]
    base, n = name, 1
    while name.lower() in used:
        n += 1
        name = f"{base[:25]}-{n}"
    used.add(name.lower())
    return name


def summary_counts(rows):
    c = {"Pass": 0, "Fail": 0, "Warning": 0, "Manual": 0, "Info": 0, "N/A": 0, "Not Tested": 0}
    for r in rows:
        c[r[3]] = c.get(r[3], 0) + 1
    return c


def write_csvs(data, outdir, base):
    checklist = data["checklist"]
    paths = []
    for res in data["results"]:
        rows = rows_for(res, checklist)
        host = (urlparse(res["url"]).netloc + urlparse(res["url"]).path).strip("/").replace("/", "_")
        host = re.sub(r"[^\w.-]", "_", host) or "page"
        p = os.path.join(outdir, f"{base}__{host}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow([f"QC Report — {res['url']}"])
            w.writerow([])
            w.writerow(COLUMNS)
            w.writerows(rows)
        paths.append(p)
    return paths


def write_xlsx(data, out, qc_by, date):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    checklist = data["checklist"]
    wb = Workbook()
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")
    center = Alignment(horizontal="center", vertical="top")

    # ---------- Summary sheet ----------
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Website QC Report"
    ws["A1"].font = Font(bold=True, size=16, color="1F3864")
    ws["A2"] = f"QC On: {qc_by or ''}"
    ws["A3"] = f"Date: {date}"
    ws["A4"] = f"Generated: {data.get('generated', '')}"
    ws["A5"] = f"Pages tested: {len(data['results'])}"
    ws.append([])
    head = ["Page URL", "WordPress", "HTTP", "Load (ms)", "Pass", "Fail", "Warning", "Manual", "Info", "N/A"]
    hr = ws.max_row + 1
    for ci, h in enumerate(head, 1):
        c = ws.cell(row=hr, column=ci, value=h)
        c.fill = header_fill; c.font = header_font; c.border = border; c.alignment = center
    for res in data["results"]:
        rows = rows_for(res, checklist)
        cnt = summary_counts(rows)
        ws.append([res["url"], "Yes" if res.get("wordpress") else "No",
                   res.get("status_code", res.get("error", "—")), res.get("load_ms", ""),
                   cnt["Pass"], cnt["Fail"], cnt["Warning"], cnt["Manual"], cnt["Info"], cnt["N/A"]])
    widths = [52, 11, 8, 10, 7, 7, 9, 9, 7, 7]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=hr + 1, max_row=ws.max_row):
        for c in row:
            c.border = border
            c.alignment = wrap if c.column == 1 else center

    # ---------- One sheet per URL ----------
    used = set()
    for res in data["results"]:
        rows = rows_for(res, checklist)
        ws = wb.create_sheet(safe_sheet_name(res["url"], used))
        ws["A1"] = f"QC Report — {res['url']}"
        ws["A1"].font = Font(bold=True, size=12, color="1F3864")
        ws["A2"] = f"QC On: {qc_by or ''}        Date: {date}"
        if res.get("error"):
            ws["A3"] = f"ERROR: {res['error']}"
            ws["A3"].font = Font(color="9C0006", bold=True)
        hr = 4
        for ci, h in enumerate(COLUMNS, 1):
            c = ws.cell(row=hr, column=ci, value=h)
            c.fill = header_fill; c.font = header_font; c.border = border; c.alignment = center
        for r in rows:
            ws.append(r)
        # style data
        for ridx, row in enumerate(ws.iter_rows(min_row=hr + 1, max_row=ws.max_row), start=hr + 1):
            status = row[3].value
            fg, fill = STATUS_FILL.get(status, ("000000", "FFFFFF"))
            for c in row:
                c.border = c.border + border if c.border else border
                c.alignment = center if c.column in (1, 4) else wrap
            row[3].font = Font(bold=True, color=fg)
            row[3].fill = PatternFill("solid", fgColor=fill)
        for col, w in zip("ABCDEF", [7, 20, 50, 11, 40, 55]):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A{hr}:F{ws.max_row}"

    wb.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description="Build QC Excel/CSV report from results.json")
    ap.add_argument("results", help="results.json from qc_scan.py")
    ap.add_argument("--out", default="QC-Report.xlsx", help="Output .xlsx path")
    ap.add_argument("--qc-by", default="", help="Tester name for the header")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="QC date")
    args = ap.parse_args()

    with open(args.results, encoding="utf-8") as fh:
        data = json.load(fh)

    outdir = os.path.dirname(os.path.abspath(args.out))
    base = os.path.splitext(os.path.basename(args.out))[0]
    csvs = write_csvs(data, outdir, base)

    xlsx = write_xlsx(data, args.out, args.qc_by, args.date)
    if xlsx:
        print(f"Excel : {xlsx}")
    else:
        print("openpyxl not available — wrote CSVs only.")
    for p in csvs:
        print(f"CSV   : {p}")


if __name__ == "__main__":
    main()
