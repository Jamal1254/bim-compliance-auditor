"""Controlled, layer-specific England Approved Document A §2C8 experiments.

Only the two leaf dimensions and the cavity width are checked here. The
applicability conditions in A §2C1–2C38, structural design, wall ties, and
the project jurisdiction/date are NOT evaluated or certified. Importantly,
a one-layer 100-mm masonry wall is not assumed to contain a cavity.
"""
import math
import re

_CAVITY = re.compile(r"\b(?:cavity|air[\s-]*gap|air[\s-]*space|void|hohlraum|luftschicht)\b", re.I)
_LEAF = re.compile(r"\b(?:brick|brickwork|masonry|block|blockwork|tijolo|alvenaria|ziegel|mauerwerk)\b", re.I)


def _positive(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None


def controlled_cavity_layer_check(wall, *, leaf_min_mm=90.0, cavity_min_mm=50.0):
    """Classify only dimensional evidence for an authored three-layer wall.

    The IFC layer set is in authoring order, which does not independently
    establish 'outer' vs 'inner' orientation. It is recorded as Leaf 1 / 2.
    """
    layers = wall.get("MaterialLayers") or []
    data = {
        "GlobalId":str(wall.get("GlobalId") or ""),
        "WallName":str(wall.get("Name") or ""),
        "IFCType":str(wall.get("Type") or ""),
        "LayerCount":len(layers),
        "LayerNames":" | ".join(str(x.get("MaterialName", "")) for x in layers),
        "ObservedLeaf1_mm":None,"ObservedCavity_mm":None,"ObservedLeaf2_mm":None,
        "ObservedTotalIFC_mm":_positive(wall.get("Width")),
        "RuleSource":"England Approved Document A §2C8 (controlled dimension-only test)",
        "MinimumLeaf_mm":leaf_min_mm,"MinimumCavity_mm":cavity_min_mm,
        "DimensionTestStatus":"EVIDENCE_INSUFFICIENT",
        "DimensionIssues":"",
        "ContractualApplicability":"NOT_VERIFIED",
        "FullBuildingCompliance":"NOT_ASSESSABLE",
        "ExperimentType":"CONTROLLED_ILLUSTRATIVE_NOT_REAL_PROJECT_CERTIFICATION",
    }
    if data["IFCType"] not in {"IfcWall","IfcWallStandardCase"}:
        data["DimensionIssues"]="Not an ordinary IfcWall material-layer assessment"
        return data
    if len(layers)!=3:
        data["DimensionIssues"]="Require exactly three declared IFC layers: masonry leaf, cavity, masonry leaf"
        return data
    names=[str(x.get("MaterialName") or "") for x in layers]
    dims=[_positive(x.get("Thickness_mm")) for x in layers]
    if not all(x is not None for x in dims):
        data["DimensionIssues"]="One or more IFC layer thicknesses are unavailable"
        return data
    if not (_LEAF.search(names[0]) and _CAVITY.search(names[1]) and _LEAF.search(names[2])):
        data["DimensionIssues"]="Layer sequence or material identity insufficient; do not infer masonry/cavity from overall thickness"
        return data
    a,c,b=dims
    data.update(ObservedLeaf1_mm=a,ObservedCavity_mm=c,ObservedLeaf2_mm=b)
    if data["ObservedTotalIFC_mm"] is not None and abs(sum(dims)-data["ObservedTotalIFC_mm"])>0.5:
        data["DimensionTestStatus"]="REVIEW_REQUIRED"
        data["DimensionIssues"]="Declared layer sum disagrees with other IFC width evidence"
        return data
    faults=[]
    if a < leaf_min_mm-1e-6: faults.append("Leaf 1 below selected minimum")
    if c < cavity_min_mm-1e-6: faults.append("Cavity below selected minimum")
    if b < leaf_min_mm-1e-6: faults.append("Leaf 2 below selected minimum")
    data["DimensionTestStatus"]=(
        "DIMENSIONAL_DEVIATION_IN_CONTROLLED_TEST" if faults else
        "DIMENSIONS_WITHIN_SELECTED_GUIDANCE"
    )
    data["DimensionIssues"]="; ".join(faults) if faults else "Leaf/cavity dimensions meet selected numerical thresholds only"
    return data


def inspect_controlled_cavity_walls(walls):
    """Pure local evaluation; never calls Gemini or Neo4j."""
    return [controlled_cavity_layer_check(w) for w in walls
            if str(w.get("Type") or "") in {"IfcWall","IfcWallStandardCase"}]
