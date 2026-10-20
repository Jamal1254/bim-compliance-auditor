"""Deterministic, explicitly scoped IFC property comparisons.

No LLM output is accepted as ground truth. The UI must distinguish user-chosen
synthetic thresholds from independently confirmed contractual rules.
"""
from dataclasses import dataclass
import math

MEASUREMENT_TYPES = {
    "Wall thickness": ("IfcWall", "IfcWallStandardCase"),
    "Door overall width": ("IfcDoor", "IfcDoorStandardCase"),
    "Door overall height": ("IfcDoor", "IfcDoorStandardCase"),
    "Window overall width": ("IfcWindow", "IfcWindowStandardCase"),
    "Window overall height": ("IfcWindow", "IfcWindowStandardCase"),
}


@dataclass(frozen=True)
class AuditRule:
    thickness_mm: float
    tolerance_mm: float = 0.0
    scope: str = "external"
    name_contains: str = ""
    global_id: str = ""
    required_materials: tuple[str, ...] = ()
    source: str = ""
    test_mode: bool = True
    metric: str = "Wall thickness"

    def __post_init__(self):
        if self.metric not in MEASUREMENT_TYPES:
            raise ValueError("Unsupported measurement type")
        if not math.isfinite(self.thickness_mm) or self.thickness_mm <= 0 or not math.isfinite(self.tolerance_mm) or self.tolerance_mm < 0:
            raise ValueError("Reference must be positive and tolerance finite and nonnegative")
        if self.scope not in {"external", "all", "name_contains", "global_id"}:
            raise ValueError("Unsupported scope")
        if self.scope == "name_contains" and not self.name_contains.strip():
            raise ValueError("Enter an element name filter")
        if self.scope == "global_id" and not self.global_id.strip():
            raise ValueError("Enter exact element GlobalId")
        if not self.source.strip():
            raise ValueError("Give a reference to the clause or synthetic experiment")
        if self.scope == "all" and not self.test_mode:
            raise ValueError("All-elements scope permitted for controlled experiments only")


def numeric_width(element):
    val = element.get("Width")
    try:
        number = float(val)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def _metric_value(element, metric):
    if metric == "Wall thickness":
        return numeric_width(element), str(element.get("WidthSource", ""))
    dims = element.get("Dimensions_mm") or {}
    key = "OverallWidth_mm" if metric.endswith("width") else "OverallHeight_mm"
    try:
        val = float(dims.get(key))
        return (val if math.isfinite(val) and val > 0 else None, f"IFC attribute: {key}")
    except (ValueError, TypeError):
        return None, f"IFC attribute: {key} not available"


def _matches_scope(e, rule):
    if rule.scope == "global_id":
        return (str(e.get("GlobalId", "")) == rule.global_id, "Different GlobalId")
    if rule.scope == "name_contains":
        return (rule.name_contains.casefold() in str(e.get("Name") or "").casefold(), "Name out of scope")
    if rule.scope == "external":
        flag = e.get("IsExternal")
        return (flag is True, "Unverified external flag" if flag is None else "Marked internal")
    return (True, "Controlled all-element scope")


def audit_elements(elements, rule):
    rows = []
    for e in elements:
        typ = str(e.get("Type") or "")
        materials = [str(v) for v in (e.get("Materials") or []) if v]
        width = numeric_width(e) if typ in MEASUREMENT_TYPES["Wall thickness"] else None
        val, source = _metric_value(e, rule.metric) if rule else (None, "Not assessed")
        row = {
            "GlobalId": str(e.get("GlobalId") or ""),
            "ElementName": str(e.get("Name") or ""), "IFCType": typ,
            "Storey": str(e.get("Storey") or "Unknown"),
            "IsExternal": e.get("IsExternal"),
            "ObservedThickness_mm": width,
            "ThicknessSource": str(e.get("WidthSource") or "Unknown"),
            "MeasurementQuality": str(e.get("MeasurementQuality") or ""),
            "Dimensions_mm": str(e.get("Dimensions_mm") or {}),
            "Measurement": rule.metric if rule else "None",
            "MeasuredValue_mm": val,
            "MeasurementSource": source,
            "ObservedMaterials": "; ".join(materials),
            "CavityWidth": str(e.get("CavityWidth") or "Not established"),
            "RequiredThickness_mm": rule.thickness_mm if rule else None,
            "Tolerance_mm": rule.tolerance_mm if rule else None,
            "RequiredMaterials": "; ".join(rule.required_materials) if rule else "",
            "EvidenceReference": rule.source if rule else "",
            "ComparisonMode": "CONTROLLED_TEST" if rule and rule.test_mode else "USER_VERIFIED_RULE" if rule else "UNVERIFIED",
            "ThicknessDifference_mm": None,
            "IssueCategory": "NOT_ASSESSABLE", "Severity": "Review",
            "Explanation": "No verified applicable measurement rule provided",
        }
        if rule is None:
            rows.append(row); continue
        if typ not in MEASUREMENT_TYPES[rule.metric]:
            row.update(IssueCategory="NOT_APPLICABLE", Explanation=f"{rule.metric} cannot be compared for {typ}")
            rows.append(row); continue
        applies, scope_note = _matches_scope(e, rule)
        if not applies:
            uncertain = rule.scope == "external" and e.get("IsExternal") is None
            row.update(IssueCategory="SCOPE_UNVERIFIED" if uncertain else "NOT_APPLICABLE", Explanation=scope_note)
            rows.append(row); continue
        if e.get("MeasurementQuality") == "CONFLICTING" and rule.metric == "Wall thickness":
            row.update(IssueCategory="REVIEW_REQUIRED", Explanation="IFC measurement sources disagree; resolve before comparison")
            rows.append(row); continue
        missing_material = bool(rule.required_materials) and not materials
        if val is None:
            label = "MISSING_BOTH" if missing_material else "MISSING_GEOMETRY"
            row.update(IssueCategory=label, Severity="Evidence gap",
                       Explanation=f"{rule.metric} not reliably extractable" +
                         (" and required material associations unavailable" if missing_material else "") +
                         "; not evidence that the physical element is defective")
            rows.append(row); continue
        if "bounding-box" in source.casefold() or "name token" in source.casefold():
            row.update(IssueCategory="REVIEW_REQUIRED", Explanation="Approximate or name-derived geometry cannot prove dimension")
            rows.append(row); continue
        if rule.required_materials and not materials:
            row.update(IssueCategory="MISSING_MATERIAL", Severity="Evidence gap",
                       Explanation="Material associations not available; not proof of physical noncompliance")
            rows.append(row); continue
        delta = round(val - rule.thickness_mm, 4)
        geometry_fail = abs(delta) > rule.tolerance_mm + 1e-9
        material_text = " ".join(materials).casefold()
        material_fail = any(w.casefold() not in material_text for w in rule.required_materials)
        category = "MISMATCH_BOTH" if geometry_fail and material_fail else "GEOMETRY_MISMATCH" if geometry_fail else "MATERIAL_MISMATCH" if material_fail else "PASS"
        row.update(
            ThicknessDifference_mm=delta, IssueCategory=category,
            Severity="None" if category == "PASS" else "Manual review",
            Explanation=f"{rule.metric}: observed {val:g} mm, reference {rule.thickness_mm:g} mm, tolerance ±{rule.tolerance_mm:g} mm. " +
            ("Text-token material test included." if rule.required_materials else "Materials not compared.")
        )
        rows.append(row)
    return rows


def categories_summary(rows):
    d = {}
    for r in rows:
        c = r["IssueCategory"]
        d[c] = d.get(c, 0) + 1
    return d


def issue_colour(category):
    return {
        "PASS":"#d5eddc", "GEOMETRY_MISMATCH":"#ffe2c2",
        "MATERIAL_MISMATCH":"#fff0bc", "MISMATCH_BOTH":"#f6c9c9",
        "MISSING_GEOMETRY":"#fbe3bd", "MISSING_MATERIAL":"#fff0bc", "MISSING_BOTH":"#f4bac4",
        "REVIEW_REQUIRED":"#e1dcfa", "SCOPE_UNVERIFIED":"#e1dcfa",
        "NOT_APPLICABLE":"#e6e6e6", "NOT_ASSESSABLE":"#e6e6e6",
    }.get(category, "#e6e6e6")
