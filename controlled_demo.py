"""Small labelled synthetic fixture for supervisor demonstrations ONLY.

Inputs are explicitly invented for deterministic category testing. They are
not a real building, not sampled ground truth, and not compliance validation.
"""
from audit_engine import AuditRule, audit_elements, categories_summary


def _wall(gid, width, materials, quality="DECLARED"):
    return {
        "GlobalId": "SYNTHETIC-" + gid,
        "Name": "SYNTHETIC " + gid,
        "Type": "IfcWallStandardCase",
        "Storey": "TEST-ONLY",
        "IsExternal": True,
        "Width": width,
        "WidthSource": "synthetic declared layer set",
        "MeasurementQuality": quality,
        "Dimensions_mm": {},
        "Materials": materials,
        "CavityWidth": "not assessed",
    }


def synthetic_classification_examples():
    elements=[
        _wall("PASS",352,["brick (352 mm)"]),
        _wall("GEOMETRY",350,["brick (350 mm)"]),
        _wall("MATERIAL",352,["concrete (352 mm)"]),
        _wall("BOTH",350,["concrete (350 mm)"]),
        _wall("MISSING_GEOMETRY","Unknown",["brick (unknown)"]),
        _wall("MISSING_MATERIAL",352,[]),
        _wall("MISSING_BOTH","Unknown",[]),
        _wall("CONFLICT",350,["brick (350 mm)"],quality="CONFLICTING"),
    ]
    rule=AuditRule(
        thickness_mm=352,tolerance_mm=0,scope="all",
        required_materials=("brick",),source="SYNTHETIC TEST REQUIREMENT (not an actual PDF clause)",
        comparison="equal",test_mode=True
    )
    rows=audit_elements(elements,rule)
    for r in rows:
        r["TruthProvenance"]="SYNTHETIC FIXTURE; NOT PROJECT DATA"
        r["ResearchGroundTruth"]="NOT A HUMAN-LABELLED CONTRACTUAL EXAMPLE"
    return rows
