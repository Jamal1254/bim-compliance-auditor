"""Wall-first workflow regression tests; no live credentials required."""
import pytest
from wall_focus import numeric_references_mm,wall_numeric_candidates,review_wall_clause

def wall(width=352):
    return {"GlobalId":"sample-wall","Type":"IfcWallStandardCase","Name":"W1",
            "Width":width,"WidthSource":"IfcMaterialLayerSet total","MeasurementQuality":"DECLARED",
            "Materials":["Masonry"],"IsExternal":False}

def passage(text="External wall total thickness shall be at least 352 mm."):
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
    with pytest.raises(ValueError,match="does not appear"):
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
