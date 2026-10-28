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


_PART_NOT_TOTAL = re.compile(
    r"\b(?:leaf|leaves|wythe|wythes|cavity|cavities|air\s*gap|insulation|"
    r"lining|plaster|render|cladding|wall\s*tie|"
    r"building\s*height|storey\s*height|story\s*height)\b",
    re.IGNORECASE,
)
_NON_THICKNESS = re.compile(
    r"\b(?:height|high|tall|storey|stories|above\s*ground|"
    r"tolerance|deviation|difference|table\s*\d+)\b",
    re.IGNORECASE,
)


def wall_thickness_references_mm(text):
    """Conservatively propose dimensions of the *whole wall* only.

    Refuse to treat cavity widths, masonry leaves, insulating layers, and
    building heights as an observed wall's total thickness. A candidate
    still needs independent confirmation of contractual applicability.
    """
    found = []
    for sentence in re.split(r"(?<=[.;])\s+|[\r\n]+", text or ""):
        low = sentence.casefold()
        # False negatives are safer here than comparing incompatible
        # physical quantities, e.g. 90-mm leaves vs 100-mm total walls.
        if _PART_NOT_TOTAL.search(low) or _NON_THICKNESS.search(low):
            continue
        if not re.search(r"\b(?:wall|walls|blockwork|masonry)\b", low):
            continue
        if not re.search(r"\b(?:thickness|thick)\b", low):
            continue
        thickness_positions = [m.start() for m in re.finditer(r"\b(?:thickness|thick)\b", low)]
        for match in _LENGTH.finditer(sentence):
            if min(abs(p - match.start()) for p in thickness_positions) > 75:
                continue
            before = sentence[max(0, match.start()-18):match.start()]
            if re.search(r"(?:[±]|\+/-)\s*$", before):
                continue
            for value in numeric_references_mm(match.group(0)):
                if value <= 2000 and value not in found:
                    found.append(value)
    return found


def wall_scope_issue(wall, text):
    """Detect obvious IFC-vs-clause scope conflicts before any PASS/FAIL."""
    low = str(text or "").casefold()
    is_external = wall.get("IsExternal")
    if re.search(r"\bexternal\s+walls?\b", low) and is_external is not True:
        return ("IFC explicitly marks wall internal" if is_external is False
                else "IFC external/internal classification unavailable")
    if re.search(r"\binternal\s+walls?\b", low) and is_external is not False:
        return ("IFC explicitly marks wall external" if is_external is True
                else "IFC external/internal classification unavailable")
    if re.search(r"\bcavity\s+walls?\b", low):
        if not isinstance(wall.get("CavityWidth"), (int, float)):
            return "Cavity-wall configuration is not established in the IFC evidence"
    if re.search(r"\bload[\s-]*bearing\b", low):
        return "Load-bearing classification is not independently established by this workflow"
    return None

def wall_numeric_candidates(candidates, limit=25):
    """Only wall passages containing an explicitly thickness-associated dimension."""
    rows = [c for c in candidates
            if "wall" in [str(x).casefold() for x in c.get("Types", ())]
            and wall_thickness_references_mm(c.get("Text", ""))]
    return rows[:limit]


def screen_wall_clause_groups(walls, candidates, *, limit=80):
    """Suggest and screen group-to-clause pairs without claiming verified links.

    Groups minimise repeated comparisons. Group membership does not establish
    contractual scope; the same property can still have different obligations.
    No LLM, database writes, or external calls are needed.
    """
    groups = {}
    for element in walls:
        materials = tuple(sorted(str(m) for m in element.get("Materials", []) if m))
        key = (str(element.get("Type") or ""), materials,
               element.get("IsExternal"), str(element.get("Width")))
        groups.setdefault(key, []).append(element)
    out = []
    for group_index, (key, members) in enumerate(sorted(groups.items(), key=lambda g: str(g[0])), 1):
        representative = members[0]
        for candidate in candidates[:limit]:
            if "wall" not in [str(v).casefold() for v in candidate.get("Types", ())]:
                continue
            text = str(candidate.get("Text") or "")
            measurements = wall_thickness_references_mm(text)
            scope_reason = wall_scope_issue(representative, text)
            if _PART_NOT_TOTAL.search(text):
                status = "INCOMPATIBLE_MEASUREMENT"
                reason = "Partial layer, cavity, lining, or insulation; not a total wall thickness rule"
            elif not measurements:
                status = "OTHER_OR_UNCLEAR_REQUIREMENT"
                reason = "No explicitly supported total wall thickness dimension in this passage"
            elif scope_reason:
                status = "SCOPE_UNVERIFIED"
                reason = scope_reason
            else:
                status = "REVIEW_CANDIDATE"
                reason = "Possible total wall thickness clause; independent document and element-scope verification still required"
            out.append({
                "Group": group_index, "IFCType": key[0],
                "WallCount": len(members),
                "ExampleGlobalId": str(representative.get("GlobalId") or ""),
                "ObservedTotalThickness_mm": representative.get("Width"),
                "ObservedExternal": representative.get("IsExternal"),
                "PDFPage": candidate.get("Page"),
                "CandidateText": text[:950],
                "PossibleTotalThickness_mm": "; ".join(str(x) for x in measurements),
                "ScreeningStatus": status, "ScreeningReason": reason,
                "ContractualApplicability": "NOT_VERIFIED",
            })
    return out

def comparable_wall_group(walls, anchor):
    """Suggest walls of the same class, material names and external flag.

    Grouping is ONLY a reviewer aid, never proof of shared contractual scope.
    """
    def signature(e):
        names = [re.sub(r"\s*\(\s*\d+(?:\.\d+)?\s*mm\s*\)", "", str(m)).strip().casefold()
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
    issue = wall_scope_issue(wall, text)
    if issue:
        raise ValueError("Clause scope is not supported for this wall: " + issue)
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
