"""Wall-first, human-verified IFC-to-PDF comparison.

A PDF fragment is a retrieval candidate only. No verdict is produced until a
reviewer confirms contractual applicability, scope and comparison semantics.
The selected numeric reference must actually appear in the cited PDF fragment.
"""
import math
import re

from audit_engine import AuditRule, audit_elements

_LENGTH = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*"
    r"(millimetres?|millimeters?|mm|centimetres?|centimeters?|cm|metres?|meters?|m|inches?|inch|in|feet|foot|ft)\b",
    re.IGNORECASE,
)
_MULTIPLIER = {
    "mm": 1, "cm": 10, "m": 1000,
    "in": 25.4, "inch": 25.4, "inches": 25.4,
    "foot": 304.8, "feet": 304.8, "ft": 304.8,
    "millimetre": 1, "millimetres": 1, "millimeter": 1, "millimeters": 1,
    "centimetre": 10, "centimetres": 10, "centimeter": 10, "centimeters": 10,
    "metre": 1000, "metres": 1000, "meter": 1000, "meters": 1000,
}


def numeric_references_mm(text):
    """Explicit dimension tokens only; never infer a wall thickness from a token."""
    found = []
    for match in _LENGTH.finditer(text or ""):
        number = float(match.group(1).replace(",", "."))
        mm = round(number * _MULTIPLIER[match.group(2).lower()], 4)
        if math.isfinite(mm) and 0 < mm < 1e7 and mm not in found:
            found.append(mm)
    return found


def wall_numeric_candidates(candidates, limit=25):
    """Keep traceable wall-category fragments containing numeric dimensions."""
    rows = [c for c in candidates
            if "wall" in [str(x).casefold() for x in c.get("Types", ())]
            and numeric_references_mm(c.get("Text", ""))]
    return rows[:limit]


def review_wall_clause(wall, candidate, required_mm, comparison, tolerance_mm, *,
                       document_confirmed=False, clause_confirmed=False):
    """Review an explicit wall/fragment pair; never certify the full project."""
    if not (document_confirmed and clause_confirmed):
        raise ValueError("Confirm the PDF belongs to the project AND the clause applies to this exact wall.")
    if not str(wall.get("Type") or "").startswith("IfcWall") or not wall.get("GlobalId"):
        raise ValueError("Choose an IFC wall with a GlobalId.")
    if "wall" not in [str(t).casefold() for t in candidate.get("Types", ())]:
        raise ValueError("Select wall-relevant PDF evidence.")
    page, text = candidate.get("Page"), str(candidate.get("Text") or "")
    if not isinstance(page, int) or page < 1 or not text.strip():
        raise ValueError("PDF page and quoted clause evidence are required.")
    try:
        required_mm = float(required_mm)
        tolerance_mm = float(tolerance_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid requirement and tolerance.") from exc
    values = numeric_references_mm(text)
    if not any(abs(x-required_mm) < 0.001 for x in values):
        raise ValueError("Selected dimension does not appear in the cited PDF extract.")
    rule = AuditRule(
        thickness_mm=required_mm, tolerance_mm=tolerance_mm,
        scope="global_id", global_id=str(wall["GlobalId"]),
        source=f"PDF page {page}: {text[:360]}",
        test_mode=False, metric="Wall thickness", comparison=comparison,
    )
    row = audit_elements([wall], rule)[0]
    row.update(PDFPage=page, PDFCandidateText=text,
               ReviewerConfirmedDocument=True, ReviewerConfirmedScope=True,
               ComparisonOperator=comparison,
               ReviewNote="Reviewer-confirmed comparison of ONE explicit wall/thickness requirement; not project certification.")
    return row
