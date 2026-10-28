"""Standalone colour-coded, source-preserving HTML audit report.

Review priority is an investigation queue, not a structural-safety severity.
HTML-escape project data because IFC and PDF content are untrusted uploads.
"""
from collections import Counter
from html import escape
from audit_engine import issue_colour

REPORT_COLUMNS = (
    "GlobalId", "ElementName", "IFCType", "ObservedThickness_mm",
    "RequiredThickness_mm", "ComparisonOperator", "IssueCategory",
    "ReviewPriority", "PDFPage", "ThicknessSource", "EvidenceReference",
)


def colour_report_html(rows, *, title="BIM Wall Evidence Report"):
    data = list(rows)
    counts = Counter(str(r.get("IssueCategory", "UNKNOWN")) for r in data)
    summary = " · ".join(f"{escape(k)}: {v}" for k,v in sorted(counts.items()))
    head = "".join(f"<th>{escape(col)}</th>" for col in REPORT_COLUMNS)
    body = []
    for row in data:
        shade = issue_colour(str(row.get("IssueCategory", "")))
        cells = "".join("<td>" + escape(str(row.get(col, "") if row.get(col) is not None else "")) + "</td>"
                        for col in REPORT_COLUMNS)
        body.append(f'<tr><td style="background:{shade};font-weight:700">{escape(str(row.get("IssueCategory", "")))}</td>{cells}</tr>')
    if not body:
        body.append('<tr><td colspan="12">No audit records</td></tr>')
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>""" + escape(title) + """</title>
<style>
body{font:14px system-ui,Arial,sans-serif;color:#1a2430;padding:28px}
h1{font-size:22px;margin:0 0 12px} .intro{color:#425363;max-width:1100px}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:20px}
th{background:#18354e;color:white;text-align:left;position:sticky;top:0}
th,td{padding:9px;border:1px solid #ddd;vertical-align:top;word-break:break-word}
tbody tr:nth-child(even){background:#f8fafc}
@media print{body{padding:8px}table{font-size:9px}th{position:static}}
</style></head><body><h1>""" + escape(title) + """</h1>
<p class="intro">Conditional, evidence-based review only. Missing evidence is not proof of physical noncompliance.
Review priorities are not structural or life-safety ratings. Contractual applicability must be independently verified.</p>
<p><b>Records:</b> """ + str(len(data)) + """</p><p><b>Statuses:</b> """ + summary + """</p>
<table><thead><tr><th>Status</th>""" + head + """</tr></thead><tbody>""" + "".join(body) + """</tbody></table>
</body></html>"""
