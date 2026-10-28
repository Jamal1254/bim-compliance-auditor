"""Wall-first workflow regression tests; no live credentials required."""
import pytest
from wall_focus import numeric_references_mm,wall_numeric_candidates,wall_thickness_references_mm,wall_scope_issue,comparable_wall_group,review_wall_clause,review_wall_batch

def wall(width=352):
    return {"GlobalId":"sample-wall","Type":"IfcWallStandardCase","Name":"W1",
            "Width":width,"WidthSource":"IfcMaterialLayerSet total","MeasurementQuality":"DECLARED",
            "Materials":["Masonry"],"IsExternal":False}

def passage(text="Wall total thickness shall be at least 352 mm."):
    return {"Page":12,"Text":text,"Types":["wall"],"Score":13}

def test_explicit_mm_conversion():
    assert numeric_references_mm("Wall 35.2 cm, 0.352 m, 352 mm") == [352.0]
    assert numeric_references_mm("450 m2 floor area") == []

def test_candidates_are_wall_only_and_numeric():
    vals=[passage(),{"Page":8,"Text":"Door width 900 mm","Types":["door"]},
          {"Page":9,"Text":"Walls shall be treated","Types":["wall"]}]
    assert wall_numeric_candidates(vals)==[vals[0]]

def test_confirmations_required():
    with pytest.raises(ValueError,match="Confirm"):
        review_wall_clause(wall(),passage(),352,"minimum",0)

def test_unquoted_numeric_rejected():
    with pytest.raises(ValueError,match="not explicitly supported"):
        review_wall_clause(wall(),passage(),400,"minimum",0,document_confirmed=True,clause_confirmed=True)

def test_minimum_vs_equal():
    p=passage("Wall minimum thickness 352 mm.")
    a=review_wall_clause(wall(355),p,352,"minimum",0,document_confirmed=True,clause_confirmed=True)
    b=review_wall_clause(wall(355),p,352,"equal",0,document_confirmed=True,clause_confirmed=True)
    assert a["IssueCategory"]=="PASS"
    assert b["IssueCategory"]=="GEOMETRY_MISMATCH"
    assert a["PDFPage"]==12 and a["GlobalId"]=="sample-wall"

def test_minimum_shortfall():
    r=review_wall_clause(wall(350.4),passage(),352,"minimum",0,
                         document_confirmed=True,clause_confirmed=True)
    assert r["IssueCategory"]=="GEOMETRY_MISMATCH"

def test_conflicting_dimensions_abstain():
    e=wall()
    e["MeasurementQuality"]="CONFLICTING"
    r=review_wall_clause(e,passage(),352,"minimum",0,
                         document_confirmed=True,clause_confirmed=True)
    assert r["IssueCategory"]=="REVIEW_REQUIRED"

def test_building_height_not_wall_thickness():
    sentence = ("Non-combustible materials in external walls of tall buildings. "
                "Building Regulations restrict materials in external walls of "
                "certain buildings over 18m in height.")
    assert wall_thickness_references_mm(sentence) == []
    assert wall_numeric_candidates([{"Page":1,"Text":sentence,"Types":["wall"]}]) == []

def test_explicit_thickness_still_detected():
    assert wall_thickness_references_mm("External masonry wall thickness must be at least 100 mm.") == [100]
    assert wall_thickness_references_mm("The walls must be at least 12 cm thick.") == [120]

def test_same_material_group_is_only_candidate():
    a = wall(100)
    b = dict(wall(120), GlobalId="second-wall", Materials=["Masonry (120 mm)"])
    a["Materials"] = ["Masonry (100 mm)"]
    c = dict(wall(100), GlobalId="third-wall", Materials=["Steel"])
    assert [w["GlobalId"] for w in comparable_wall_group([a,b,c],a)] == ["sample-wall","second-wall"]

def test_batch_verification_and_scope():
    a=wall(352)
    b=dict(wall(350),GlobalId="other-wall")
    with pytest.raises(ValueError,match="every selected wall"):
        review_wall_batch([a,b],passage(),352,"minimum",0,
                          document_confirmed=True,clause_confirmed=True)
    checked=review_wall_batch([a,b],passage(),352,"minimum",0,
                              document_confirmed=True,clause_confirmed=True,
                              batch_scope_confirmed=True)
    assert [x["IssueCategory"] for x in checked] == ["PASS","GEOMETRY_MISMATCH"]


def test_pdf_leaf_and_cavity_requirements_never_become_total_wall_thickness():
    text = ("blockwork: All cavity walls should have leaves at least 90mm thick "
            "and cavities at least 50mm wide. The wall ties should have a horizontal")
    assert wall_thickness_references_mm(text) == []
    assert wall_numeric_candidates([{"Page": 9, "Text": text, "Types": ["wall"]}]) == []
    with pytest.raises(ValueError, match="not explicitly supported|Clause scope"):
        review_wall_clause(wall(100), {"Page":9,"Text":text,"Types":["wall"]},
                           90, "minimum", 0, document_confirmed=True, clause_confirmed=True)


def test_external_scope_mismatch_not_silently_passed():
    external_passage = passage("External wall total thickness must be at least 100 mm.")
    assert "internal" in wall_scope_issue(wall(100), external_passage["Text"])
    with pytest.raises(ValueError, match="Clause scope"):
        review_wall_clause(wall(100), external_passage, 100, "minimum", 0,
                           document_confirmed=True, clause_confirmed=True)
    external_wall = dict(wall(100),IsExternal=True)
    assert review_wall_clause(external_wall, external_passage, 100, "minimum", 0,
                              document_confirmed=True, clause_confirmed=True)["IssueCategory"] == "PASS"


def test_load_bearing_scope_requires_specific_classification():
    statement = passage("Load-bearing masonry wall thickness shall be at least 150 mm.")
    assert "Load-bearing" in wall_scope_issue(wall(150), statement["Text"])
    with pytest.raises(ValueError, match="Load-bearing"):
        review_wall_clause(wall(150), statement, 150, "minimum", 0,
                           document_confirmed=True, clause_confirmed=True)


def test_reject_layer_partial_thickness_with_numeric_total_same_fragment():
    mixed = "Wall leaf thickness 90 mm. Masonry cavity width 50 mm."
    assert wall_thickness_references_mm(mixed) == []
    assert wall_thickness_references_mm("All masonry walls require a minimum TOTAL wall thickness of 150 mm.") == [150]
