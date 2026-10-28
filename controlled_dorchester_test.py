"""Dorchester sample PDF / IFC controlled nominal-assembly comparison.

This module is an evidence-only, designed experiment, NOT a verified
contractual compliance check. One exported wall layer is not automatically a
three-part brick / cavity / block wall, even when its total is ~352 mm.
"""
import math
import re

_BRICK = re.compile(r"\b(?:brick|brickwork|ziegel|tijolo)\b", re.I)
_CAVITY = re.compile(r"\b(?:cavity|air[\s-]*gap|air[\s-]*space|void|luftschicht|hohlraum)\b", re.I)
_BLOCK = re.compile(r"\b(?:block|blockwork|aircrete|concrete block|masonry block)\b", re.I)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def is_dorchester_352_source(source_rows):
    """Only show this experiment if the supplied PDF itself supplies 352 mm."""
    return any(
        _number(row.get("AssemblyThickness_mm")) == 352
        and row.get("AssemblyKind") in {"cavity wall construction", "facing masonry"}
        and re.search(r"\b352\s*mm\b", str(row.get("QuotedLine","")), re.I)
        for row in source_rows
    )


def nominal_cavity_352_case(wall, *, source_page):
    """Evaluate declared core layers; preserve all unknown conditions.

    Assumes an expressly authored three-part *test* wall with layer order
    brick / cavity / block. Nominal values 102+150+100 come from the
    Dorchester sample, not universal English Building Regulations. No
    tolerance is inferred; differences are only reported, not violations.
    """
    layers=wall.get("MaterialLayers") or []
    observed_total=_number(wall.get("Width"))
    result={
        "GlobalId":str(wall.get("GlobalId","")),
        "WallName":str(wall.get("Name","")),
        "IFCType":str(wall.get("Type","")),
        "Storey":str(wall.get("Storey","")),
        "SourcePDFPage":int(source_page),
        "SourceClause":"Dorchester sample: nominal 352 mm brick/cavity/block assembly",
        "IFCLayerCount":len(layers),
        "IFCLayerNames":" | ".join(str(x.get("MaterialName","")) for x in layers),
        "ExpectedBrick_mm":102.0,
        "ExpectedCavity_mm":150.0,
        "ExpectedBlock_mm":100.0,
        "ExpectedCoreAssembly_mm":352.0,
        "IFCBrick_mm":None,
        "IFCCavity_mm":None,
        "IFCBlock_mm":None,
        "IFCOverallThickness_mm":observed_total,
        "BrickDifference_mm":None,
        "CavityDifference_mm":None,
        "BlockDifference_mm":None,
        "CoreDifference_mm":None,
        "ControlledDimensionStatus":"EVIDENCE_INSUFFICIENT",
        "Reason":"",
        "ExperimentKind":"CONTROLLED_REVIT_EXPORT_CHECK_NOT_REAL_CONTRACT_CERTIFICATION",
        "DocumentAppliesToModel":"NOT_ESTABLISHED",
        "RealComplianceVerdict":"NOT_ASSESSABLE",
    }
    if result["IFCType"] not in {"IfcWall","IfcWallStandardCase"}:
        result["Reason"]="Not an ordinary masonry wall-class element"
        return result
    if len(layers)!=3:
        result["Reason"]="No three-layer brick/cavity/block assembly established in exported IFC"
        return result
    names=[str(row.get("MaterialName") or "") for row in layers]
    if not (_BRICK.search(names[0]) and _CAVITY.search(names[1]) and _BLOCK.search(names[2])):
        result["Reason"]="IFC layer names/order do not independently establish brick, cavity, block roles"
        return result
    thicknesses=[_number(row.get("Thickness_mm")) for row in layers]
    if any(x is None for x in thicknesses):
        result["Reason"]="One or more IFC material-layer dimensions missing"
        return result
    brick,cavity,block=thicknesses
    result.update(
        IFCBrick_mm=brick,IFCCavity_mm=cavity,IFCBlock_mm=block,
        BrickDifference_mm=round(brick-102,4),
        CavityDifference_mm=round(cavity-150,4),
        BlockDifference_mm=round(block-100,4),
        CoreDifference_mm=round(sum(thicknesses)-352,4),
    )
    if observed_total is not None and abs(sum(thicknesses)-observed_total)>0.5:
        result["ControlledDimensionStatus"]="REVIEW_REQUIRED"
        result["Reason"]="IFC total thickness and three material-layer dimensions disagree"
    elif all(abs(delta)<1e-6 for delta in (
            result["BrickDifference_mm"],result["CavityDifference_mm"],
            result["BlockDifference_mm"])):
        result["ControlledDimensionStatus"]="MATCHES_SELECTED_NOMINAL_LAYER_VALUES"
        result["Reason"]="Declared three-part IFC dimensions equal the PDF nominal layer values; scope unverified"
    else:
        result["ControlledDimensionStatus"]="DIFFERS_FROM_SELECTED_NOMINAL_LAYER_VALUES"
        result["Reason"]="One or more IFC layer dimensions differ from the PDF nominal design; no tolerance or scope inferred"
    return result


def evaluate_nominal_cavity_352(walls, source_rows):
    """Return source-linked, all-wall evidence for a controlled Revit test."""
    if not is_dorchester_352_source(source_rows):
        return []
    selected=next(row for row in source_rows
                  if _number(row.get("AssemblyThickness_mm")) == 352
                  and row.get("AssemblyKind") in {"cavity wall construction","facing masonry"}
                  and re.search(r"\b352\s*mm\b",str(row.get("QuotedLine","")),re.I))
    return [nominal_cavity_352_case(w,source_page=selected["PDFPage"]) for w in walls
            if str(w.get("Type") or "") in {"IfcWall","IfcWallStandardCase"}]
