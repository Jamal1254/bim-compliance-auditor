"""Numerical proximity is NOT proof of IFC ↔ specification applicability."""
import pytest
from assembly_evidence import numerical_wall_assembly_neighbours

def sample(width=350.0, gid="wall-1", typ="IfcWallStandardCase"):
    return {"Type":typ,"Name":"Existing masonry", "GlobalId":gid,
            "Width":width,"WidthSource":"IfcMaterialLayerSet total",
            "Materials":["Existing masonry (350 mm)"],"Storey":"L2","IsExternal":True}

def rule():
    return {"PDFPage":14,"AssemblyThickness_mm":352,"QuotedLine":"352mm cavity wall construction"}

def test_nominal_352_numeric_neighbours_not_mismatch():
    out=numerical_wall_assembly_neighbours([sample(350.0),sample(350.04375,"wall-2"),
                                          sample(100,"wall-3")],rule())
    assert len(out)==2
    assert [x["SignedNumericalDifference_mm"] for x in out]==[-1.9562,-2.0]
    assert all(x["ComplianceVerdict"]=="NOT_ASSESSABLE" for x in out)
    assert all(x["ContractualApplicability"]=="NOT_VERIFIED" for x in out)
    assert all(x["PropertyComparability"]=="NOT_VERIFIED" for x in out)

def test_no_curtaill_wall_and_unknown_thickness():
    out=numerical_wall_assembly_neighbours([
        sample(350,"curtain","IfcCurtainWall"),
        sample("Unknown","unknown"),
        sample(350,"actual-wall")],rule())
    assert [r["GlobalId"] for r in out] == ["actual-wall"]

def test_proximity_is_not_construction_tolerance():
    out=numerical_wall_assembly_neighbours([sample(349)],rule(),window_mm=2)
    assert out==[]
    assert numerical_wall_assembly_neighbours([sample(350)],rule(),window_mm=2)[0]["DiscoveryWindow_mm_NOT_TOLERANCE"]==2
    with pytest.raises(ValueError):
        numerical_wall_assembly_neighbours([],rule(),window_mm=-1)
