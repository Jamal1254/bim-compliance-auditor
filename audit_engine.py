"""Deterministic element-level checking for a human-confirmed contract clause.

This does NOT infer that an arbitrary contract is applicable to an IFC model.
The user must explicitly supply a verified rule, element scope, and reference.
"""
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class AuditRule:
    thickness_mm: float
    tolerance_mm: float = 0.0
    scope: str = "external"  # external, all, name_contains
    name_contains: str = ""
    required_materials: tuple[str, ...] = ()
    source: str = "Human-confirmed contractual requirement"

    def __post_init__(self):
        if self.thickness_mm <= 0 or self.tolerance_mm < 0:
            raise ValueError("Thickness must be positive and tolerance non-negative.")
        if self.scope not in {"external", "all", "name_contains"}:
            raise ValueError("Unknown scope")
        if self.scope == "name_contains" and not self.name_contains.strip():
            raise ValueError("Provide a name substring for name_contains scope")


def _dimension(element):
    v = element.get("Width")
    if isinstance(v, bool):
        return None
    if isinstance(v, (float, int)):
        return float(v) if v > 0 else None
    if isinstance(v, str):
        try:
            return float(v.strip()) if float(v.strip()) > 0 else None
        except ValueError:
            return None
    return None


def _scope_applies(element, rule):
    if rule.scope == "all":
        return True, ""
    if rule.scope == "name_contains":
        applicable = rule.name_contains.lower() in (element.get("Name") or "").lower()
        return applicable, "Element name does not match selected scope" if not applicable else ""
    # `False` and `None` must not be treated as equivalent: unknown = review.
    is_external = element.get("IsExternal")
    if is_external is True:
        return True, ""
    if is_external is False:
        return False, "Element explicitly marked internal"
    return False, "External/internal classification not established"


def audit_elements(elements: Sequence[dict], rule: Optional[AuditRule]):
    """Return one reproducible record per IFC GlobalId (not per wall type)."""
    result = []
    for element in elements:
        gid = str(element.get("GlobalId") or "")
        name = str(element.get("Name") or "")
        typ = str(element.get("Type") or "")
        width = _dimension(element)
        materials = element.get("Materials") or []
        materials_text = "; ".join(str(v) for v in materials)
        row = {
            "GlobalId": gid, "Name": name, "Type": typ,
            "Storey": element.get("Storey", "Unknown"),
            "IsExternal": element.get("IsExternal"),
            "ObservedThickness_mm": width,
            "ThicknessSource": element.get("WidthSource", "Not recorded"),
            "ObservedMaterials": materials_text,
            "RequiredThickness_mm": rule.thickness_mm if rule else None,
            "Tolerance_mm": rule.tolerance_mm if rule else None,
            "RequiredMaterials": "; ".join(rule.required_materials) if rule else "",
            "SpecificationReference": rule.source if rule else "",
            "ThicknessDifference_mm": None, "IssueCategory": "UNASSESSED",
            "Severity": "Review", "Explanation": "No human-confirmed rule supplied",
        }
        if rule is None:
            result.append(row)
            continue
        applies, reason = _scope_applies(element, rule)
        if not applies:
            row.update(IssueCategory="NOT_APPLICABLE", Severity="Review", Explanation=reason)
            result.append(row)
            continue
        # Only claim a status when a user-confirmed rule applies.
        has_geometry = width is not None
        material_check = bool(rule.required_materials)
        has_material = bool(materials)
        absent = {"geometry": not has_geometry, "material": material_check and not has_material}
        if any(absent.values()):
            if absent["geometry"] and absent["material"]:
                category = "MISSING_BOTH"
            elif absent["geometry"]:
                category = "MISSING_GEOMETRY"
            else:
                category = "MISSING_MATERIAL"
            row.update(IssueCategory=category, Severity="High", Explanation="Required IFC information unavailable")
            result.append(row)
            continue
        diff = round(width - rule.thickness_mm, 3)
        mismatch_geo = abs(diff) > rule.tolerance_mm + 1e-9
        lower = materials_text.lower()
        mismatch_material = any(term.lower() not in lower for term in rule.required_materials)
        if mismatch_geo and mismatch_material:
            category = "MISMATCH_BOTH"
        elif mismatch_geo:
            category = "GEOMETRY_MISMATCH"
        elif mismatch_material:
            category = "MATERIAL_MISMATCH"
        else:
            category = "PASS"
        row.update(
            ThicknessDifference_mm=diff,
            IssueCategory=category,
            Severity="High" if category != "PASS" else "None",
            Explanation=(f"Actual {width:g} mm vs required {rule.thickness_mm:g} mm; "
                         f"allowable difference {rule.tolerance_mm:g} mm. "
                         f"Materials were {'checked' if material_check else 'not assessed'}.")
        )
        result.append(row)
    return result


def categories_summary(rows):
    counts = {}
    for row in rows:
        x = row["IssueCategory"]
        counts[x] = counts.get(x, 0) + 1
    return counts


def issue_colour(category):
    """CSS background colours are DISPLAY only, not engineering hazard levels."""
    return {
        "PASS": "#d4edda",
        "GEOMETRY_MISMATCH": "#ffe5c2", "MATERIAL_MISMATCH": "#fff3cd",
        "MISMATCH_BOTH": "#f8d7da", "MISSING_BOTH": "#f8d7da",
        "MISSING_GEOMETRY": "#ffe5c2", "MISSING_MATERIAL": "#fff3cd",
        "NOT_APPLICABLE": "#e9ecef", "UNASSESSED": "#e9ecef",
    }.get(category, "#e9ecef")
