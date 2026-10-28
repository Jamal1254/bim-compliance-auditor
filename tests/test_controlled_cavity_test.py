"""AD A 2C8 controlled study: dimension-only, never building certification."""
import pytest
import spec_context
from controlled_cavity_test import controlled_cavity_layer_check,inspect_controlled_cavity_walls


def wall(layers, width=None, gid="test-wall"):
    names=[l[0] for l in layers]
    thickness=[l[1] for l in layers]
    return {"GlobalId":gid,"Type":"IfcWallStandardCase","Name":"CONTROLLED REVT STUDY",
            "Width":width if width is not None else sum(thickness),
            "MaterialLayers":[{"LayerIndex":i+1,"MaterialName":n,
                               "Thickness_mm":t,
                               "EvidenceSource":"IfcMaterialLayerSet.MaterialLayers"}
                              for i,(n,t) in enumerate(layers)]}


def test_positive_and_two_negative_controlled_experiments():
    cases=[
        ([("Brick outer leaf",100),("Air gap cavity",50),("Block inner leaf",100)],
         "DIMENSIONS_WITHIN_SELECTED_GUIDANCE",[]),
        ([("Brick outer leaf",80),("Air gap cavity",50),("Block inner leaf",100)],
         "DIMENSIONAL_DEVIATION_IN_CONTROLLED_TEST",["Leaf 1"]),
        ([("Brick outer leaf",100),("Air gap cavity",40),("Block inner leaf",100)],
         "DIMENSIONAL_DEVIATION_IN_CONTROLLED_TEST",["Cavity"]),
    ]
    for layers,expected,tokens in cases:
        r=controlled_cavity_layer_check(wall(layers))
        assert r["DimensionTestStatus"]==expected
        assert all(t in r["DimensionIssues"] for t in tokens)
        assert r["FullBuildingCompliance"]=="NOT_ASSESSABLE"
        assert r["ContractualApplicability"]=="NOT_VERIFIED"


def test_original_multifamiliar_single_100mm_layer_abstains():
    row=controlled_cavity_layer_check(wall([(".Alvenaria_Tijolo",100)]))
    assert row["DimensionTestStatus"]=="EVIDENCE_INSUFFICIENT"
    assert "three declared IFC layers" in row["DimensionIssues"]
    assert row["FullBuildingCompliance"]=="NOT_ASSESSABLE"


def test_invalid_layer_names_and_conflicting_ifc_width_are_reviewable():
    names=wall([("Plaster",100),("Unknown",50),("Paint",100)])
    assert controlled_cavity_layer_check(names)["DimensionTestStatus"]=="EVIDENCE_INSUFFICIENT"
    invalid=wall([("Brick",100),("Cavity",50),("Block",100)],width=260)
    assert controlled_cavity_layer_check(invalid)["DimensionTestStatus"]=="REVIEW_REQUIRED"


def test_source_page_and_thresholds_cited_from_actual_pdf_text(monkeypatch):
    paragraph=("A1/2 Section 2C: Thickness of walls in certain small buildings "
        "2C8 Cavity walls in coursed brickwork or blockwork: All cavity walls "
        "should have leaves at least 90mm thick and cavities at least 50mm wide.")
    class Page:
        def __init__(self,t):self.t=t
        def extract_text(self):return self.t
    class Reader:
        def __init__(self,_):self.pages=[Page("Unrelated 90mm and 50mm"),Page(paragraph)]
    monkeypatch.setattr(spec_context,"PdfReader",Reader)
    refs=spec_context.find_ad_a_2c8_cavity_guidance(b"mock")
    assert len(refs)==1 and refs[0]["PDFPage"]==2
    assert refs[0]["MinimumMasonryLeaf_mm"]==90
    assert refs[0]["MinimumCavity_mm"]==50
    assert refs[0]["Applicability"]=="UNVERIFIED_SECTION_2C_CONDITIONS"


def test_nonwall_is_never_given_a_wall_experiment_result():
    x=wall([("Brick",100),("Cavity",50),("Block",100)])
    x["Type"]="IfcDoor"
    assert controlled_cavity_layer_check(x)["DimensionTestStatus"]=="EVIDENCE_INSUFFICIENT"
    assert inspect_controlled_cavity_walls([x])==[]
