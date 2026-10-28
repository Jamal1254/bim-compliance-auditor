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


def wall_thickness_references_mm(text):
    """Conservative candidates for wall *thickness*, not unrelated building height.

    A number is not a thickness merely because it appears in a wall-related
    paragraph. The human reviewer still has to confirm the clause.
    """
    supported = []
    for sentence in re.split(r"(?<=[.;])\\s+|[\\r\\n]+", text or ""):
        positions = [m.start() for m in re.finditer(r"\\b(?:thickness|thick)\\b", sentence, re.I)]
        if not positions:
            continue
        for match in _LENGTH.finditer(sentence):
            before = sentence[max(0, match.start()-55):match.start()].casefold()
            after = sentence[match.end():match.end()+40].casefold()
            context = before + " " + after
            if min(abs(p-match.start()) for p in positions) > 75:
                continue
            # These often express building height, not physical wall thickness.
            if re.search(r"\\b(?:height|high|tall|storey|stories|above ground)\\b", context):
                continue
            # A tolerance or a table reference is not the actual requirement.
            if re.search(r"\\b(?:tolerance|deviation|difference|table\\s*\\d+)\\b", context):
                continue
            if re.search(r"(?:[±]|\\+/-|\\-\\s*)\\s*$", before):
                continue
            numeric = numeric_references_mm(match.group(0))
            if numeric and numeric[0] <= 2000 and numeric[0] not in supported:
                supported.append(numeric[0])
    return supported


def wall_numeric_candidates(candidates, limit=25):
    """Only wall passages containing an explicitly thickness-associated dimension."""
    rows = [c for c in candidates
            if "wall" in [str(x).casefold() for x in c.get("Types", ())]
            and wall_thickness_references_mm(c.get("Text", ""))]
    return rows[:limit]


def comparable_wall_group(walls, anchor):
    """Suggest walls of the same class, material names and external flag.

    Grouping is ONLY a reviewer aid, never proof of shared contractual scope.
    """
    def signature(e):
        names = [re.sub(r"\\s*\\(\\s*\\d+(?:\\.\\d+)?\\s*mm\\s*\\)", "", str(m)).strip().casefold()
                 for m in e.get("Materials", [])]
        return (e.get("Type"), tuple(sorted(names)), e.get("IsExternal"))
    sig = signature(anchor)
    return [e for e in walls if signature(e) == sig]


def review_wall_batch(walls, candidate, required_mm, comparison, tolerance_mm, *,
                      document_confirmed=False, clause_confirmed=False,
                      batch_scope_confirmed=False):
    """Deterministically compare selected walls using one independently verified clause."""
    items = list(walls)
    if not items:
        raise ValueError("Select at least one wall.")
    ids = [str(e.get("GlobalId") or "") for e in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Selected walls include duplicate GlobalIds.")
    if len(items) > 1 and not batch_scope_confirmed:
        raise ValueError("Confirm applicability to every selected wall before batch comparison.")
    return [review_wall_clause(e, candidate, required_mm, comparison, tolerance_mm,
                               document_confirmed=document_confirmed,
                               clause_confirmed=clause_confirmed) for e in items]


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
    values = wall_thickness_references_mm(text)
    if not any(abs(x-required_mm) < 0.001 for x in values):
        raise ValueError("Selected dimension is not explicitly supported as a wall thickness in this PDF passage.")
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
