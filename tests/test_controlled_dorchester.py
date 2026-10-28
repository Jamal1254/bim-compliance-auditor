"""Regression: user-controlled Revit modifications vs the actual Dorchester nominal assembly."""
import pytest
from controlled_dorchester_test import (
    is_dorchester_352_source, nominal_cavity_352_case, evaluate_nominal_cavity_352,
)


def source(page=14):
    return {"AssemblyThickness_mm":352.0,
            "AssemblyKind":"cavity wall construction",
            "PDFPage":page,
            "QuotedLine":"352mm cavity wall construction for 2 Storey Houses"}


def wall(three, name="EXP-CAVITY-A", width=None, gid="W1"):
    return {"GlobalId":gid,"Name":name,"Type":"IfcWallStandardCase",
            "Storey":"L2","Width":sum(t for n,t in three) if width is None else width,
            "MaterialLayers":[{"LayerIndex":i,"MaterialName":n,"Thickness_mm":t}
                              for i,(n,t) in enumerate(three,1)]}


def test_three_independent_revit_design_controls_are_identified():
    original = wall([("Brick outer leaf",102),("Air gap cavity",150),("Block inner leaf",100)])
    cavity = wall([("Brick outer leaf",102),("Air gap cavity",140),("Block inner leaf",100)],
                  name="EXP-CAVITY-B",gid="W2")
    block = wall([("Brick outer leaf",102),("Air gap cavity",150),("Block inner leaf",90)],
                 name="EXP-CAVITY-C",gid="W3")
    out = evaluate_nominal_cavity_352([original,cavity,block], [source()])
    assert [x["ControlledDimensionStatus"] for x in out] == [
        "MATCHES_SELECTED_NOMINAL_LAYER_VALUES",
        "DIFFERS_FROM_SELECTED_NOMINAL_LAYER_VALUES",
        "DIFFERS_FROM_SELECTED_NOMINAL_LAYER_VALUES",
    ]
    assert out[1]["CavityDifference_mm"]==-10
    assert out[1]["BlockDifference_mm"]==0
    assert out[2]["CavityDifference_mm"]==0
    assert out[2]["BlockDifference_mm"]==-10
    assert all(x["DocumentAppliesToModel"]=="NOT_ESTABLISHED" for x in out)
    assert all(x["RealComplianceVerdict"]=="NOT_ASSESSABLE" for x in out)


def test_original_one_layer_350mm_wall_abstains_not_a_fake_mismatch():
    original=wall([("Mauerwerk - ohne Daemmeigenschaften",350.04375)])
    result=nominal_cavity_352_case(original,source_page=14)
    assert result["ControlledDimensionStatus"]=="EVIDENCE_INSUFFICIENT"
    assert result["RealComplianceVerdict"]=="NOT_ASSESSABLE"
    assert result["IFCLayerCount"]==1


def test_three_generic_layers_do_not_prove_masonry_cavity():
    bad=wall([("Generic 1",102),("Generic 2",150),("Generic 3",100)])
    assert nominal_cavity_352_case(bad,source_page=14)["ControlledDimensionStatus"]=="EVIDENCE_INSUFFICIENT"


def test_contradictory_total_is_review_required():
    w=wall([("Brick",102),("Cavity",150),("Block",100)],width=370)
    assert nominal_cavity_352_case(w,source_page=14)["ControlledDimensionStatus"]=="REVIEW_REQUIRED"


def test_dorchester_source_is_required_no_arbitrary_pdf_defaults():
    ok=[source()]
    assert is_dorchester_352_source(ok)
    assert not is_dorchester_352_source([{"AssemblyThickness_mm":350,
        "AssemblyKind":"cavity wall construction","QuotedLine":"350mm cavity wall construction"}])
    assert evaluate_nominal_cavity_352([wall([("Brick",102),("Cavity",150),("Block",100)])],[])==[]


def test_non_wall_not_checked():
    e=wall([("Brick",102),("Cavity",150),("Block",100)])
    e["Type"]="IfcCurtainWall"
    assert evaluate_nominal_cavity_352([e],[source()])==[]
