"""Auditable element-by-element dimensional rules.

No IFC element can be declared compliant unless a user has independently
verified the reference clause AND confirmed that it applies to the model.
Synthetic probes are labelled tests, never actual building-code approvals.
"""
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class AuditRule:
    thickness_mm: float
    tolerance_mm: float = 0.0
    scope: str = "external"  # external, all, name_contains
    name_contains: str = ""
    global_id: str = ""
    required_materials: tuple[str, ...] = ()
    source: str = ""
    test_mode: bool = True

    def __post_init__(self):
        if self.thickness_mm <= 0 or self.tolerance_mm < 0:
            raise ValueError("Required thickness must be positive; tolerance cannot be negative.")
        if self.scope not in {"external", "all", "name_contains", "global_id"}:
            raise ValueError("Unsupported scope")
        if self.scope == "name_contains" and not self.name_contains.strip():
            raise ValueError("Enter a nonempty element name filter.")
        if self.scope == "global_id" and not self.global_id.strip():
            raise ValueError("Enter one complete GlobalId for the selected test")
        if not self.source.strip():
            raise ValueError("Provide an exact human-confirmed specification citation or test reference.")
        if not self.test_mode and self.scope == "all":
            raise ValueError("All-elements scope is only permitted in controlled test mode.")


def numeric_width(element):
    value = element.get("Width")
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
        return v if 0 < v < float("inf") else None
    except (TypeError, ValueError):
        return None


def _scope(element, rule):
    if rule.scope == "global_id":
        matched = str(element.get("GlobalId") or "") == rule.global_id
        return matched, "Different GlobalId" if not matched else ""
    if rule.scope == "all":
        return True, "All elements: controlled test only"
    if rule.scope == "name_contains":
        found = rule.name_contains.casefold() in str(element.get("Name") or "").casefold()
        return found, "Name not within declared rule scope" if not found else ""
    if element.get("IsExternal") is True:
        return True, ""
    if element.get("IsExternal") is False:
        return False, "IFC marks the element internal"
    return False, "External/internal classification is unknown"


def audit_elements(elements: Sequence[dict], rule: Optional[AuditRule]):
    """One non-authoritative row per IFC GlobalId. No inference of contract applicability."""
    rows = []
    for e in elements:
        materials = [str(v) for v in (e.get("Materials") or []) if v]
        material_text = "; ".join(materials)
        width = numeric_width(e)
        record = {
            "GlobalId": str(e.get("GlobalId") or ""),
            "ElementName": str(e.get("Name") or ""),
            "IFCType": str(e.get("Type") or ""),
            "Storey": str(e.get("Storey") or "Unknown"),
            "IsExternal": e.get("IsExternal"),
            "ObservedThickness_mm": width,
            "ThicknessSource": str(e.get("WidthSource") or "Unknown"),
            "ObservedMaterials": material_text,
            "CavityWidth": str(e.get("CavityWidth") or "Not recorded"),
            "RequiredThickness_mm": rule.thickness_mm if rule else None,
            "Tolerance_mm": rule.tolerance_mm if rule else None,
            "RequiredMaterials": "; ".join(rule.required_materials) if rule else "",
            "EvidenceReference": rule.source if rule else "",
            "ComparisonMode": "CONTROLLED_TEST" if rule and rule.test_mode else "VERIFIED_RULE" if rule else "UNVERIFIED",
            "ThicknessDifference_mm": None,
            "IssueCategory": "NOT_ASSESSABLE",
            "Severity": "Review",
            "Explanation": "No verified applicable rule was supplied",
        }
        if rule is None:
            rows.append(record)
            continue
        # Only actual wall entities can be evaluated with a wall-thickness rule.
        if str(e.get("Type") or "") not in {"IfcWall", "IfcWallStandardCase"}:
            record.update(IssueCategory="NOT_APPLICABLE",
                          Explanation="Wall thickness rule not applicable to this IFC element type")
            rows.append(record)
            continue
        applies, reason = _scope(e, rule)
        if not applies:
            uncertainty = rule.scope == "external" and e.get("IsExternal") is None
            record.update(IssueCategory="SCOPE_UNVERIFIED" if uncertainty else "NOT_APPLICABLE", Explanation=reason)
            rows.append(record)
            continue
        if width is None:
            category = "MISSING_BOTH" if rule.required_materials and not materials else "MISSING_GEOMETRY"
            record.update(IssueCategory=category, Explanation="Model width could not be extracted (not proof of a missing modeled dimension)")
            rows.append(record)
            continue
        # Bounding boxes approximate widths, particularly when walls are rotated,
        # curved or irregular. An exact contractual comparison cannot be certified.
        if "bounding-box" in str(e.get("WidthSource", "")).lower():
            record.update(IssueCategory="REVIEW_REQUIRED", Explanation="Width is only an axis-aligned bounding-box approximation")
            rows.append(record)
            continue
        if rule.required_materials and not materials:
            record.update(IssueCategory="MISSING_MATERIAL", Explanation="Material properties not retrieved from IFC")
            rows.append(record)
            continue
        diff = round(width - rule.thickness_mm, 3)
        geometry_bad = abs(diff) > rule.tolerance_mm + 1e-9
        material_bad = any(term.casefold() not in material_text.casefold() for term in rule.required_materials)
        if geometry_bad and material_bad:
            issue = "MISMATCH_BOTH"
        elif geometry_bad:
            issue = "GEOMETRY_MISMATCH"
        elif material_bad:
            issue = "MATERIAL_MISMATCH"
        else:
            issue = "PASS"
        record.update(
            ThicknessDifference_mm=diff,
            IssueCategory=issue,
            Severity="None" if issue == "PASS" else "Review required",
            Explanation=(f"Observed {width:g} mm; reference {rule.thickness_mm:g} mm; "
                         f"tolerance +/-{rule.tolerance_mm:g} mm. "
                         f"{'Material keywords checked.' if rule.required_materials else 'Materials not part of rule.'}"),
        )
        rows.append(record)
    return rows


def categories_summary(rows):
    result = {}
    for row in rows:
        k = row["IssueCategory"]
        result[k] = result.get(k, 0) + 1
    return result


def issue_colour(category):
    return {
        "PASS": "#d5eddc",
        "GEOMETRY_MISMATCH": "#ffe2c2",
        "MATERIAL_MISMATCH": "#fff0bc",
        "MISMATCH_BOTH": "#f6c9c9",
        "MISSING_BOTH": "#f6c9c9",
        "MISSING_GEOMETRY": "#fbe3bd",
        "MISSING_MATERIAL": "#fff0bc",
        "REVIEW_REQUIRED": "#e1dcfa",
        "SCOPE_UNVERIFIED": "#e1dcfa",
        "NOT_APPLICABLE": "#e6e6e6",
        "NOT_ASSESSABLE": "#e6e6e6",
    }.get(category, "#e6e6e6")
