"""Regress the supervisor's specific element-linking objective, without live APIs."""
from semantic_links import (
    rank_element_requirement_candidates, select_graph_elements,
    format_grounded_link_context,
)


def wall(gid, width, materials, external=True):
    return {
        "GlobalId":gid,"Type":"IfcWallStandardCase","Name":"Wall-"+gid,
        "Width":width,"WidthSource":"IfcMaterialLayerSet total",
        "Storey":"L2","IsExternal":external,"Materials":materials,
    }


def assembly():
    return [{
        "PDFPage":14,
        "AssemblyThickness_mm":352,
        "QuotedLine":"352mm cavity wall construction for a minimum of 3 courses below dpc",
        "SurroundingText":"External Masonry Walls; 2 Storey Houses; "
                          "352mm cavity wall construction; 102mm outer leaf brickwork; "
                          "150mm cavity; 100mm inner blockwork",
    }]


def test_realistic_project11_candidate_is_not_contractual_fail():
    elements=[
        wall("one-350",350,["Mauerwerk - ohne Daemmeigenschaften (350 mm)"]),
        wall("one-35004",350.04375,["Ortbeton - C30/37 Verputzt (350 mm)"]),
        wall("one-100",100,["Masonry (100 mm)"]),
    ]
    links=rank_element_requirement_candidates(elements, assembly(),max_pairs=10)
    assert links[0]["GlobalId"]=="one-35004"
    assert links[0]["PDFPage"]==14
    assert links[0]["ObservedThickness_mm"]==350.04375
    assert links[0]["ScreeningStatus"]=="ASSEMBLY_NOT_ESTABLISHED"
    assert all(p["ComplianceVerdict"]=="NOT_ASSESSABLE" for p in links)
    assert all(p["ContractualApplicability"]=="NOT_VERIFIED" for p in links)
    assert "Mauerwerk" in links[1]["IFCMaterials"]


def test_graph_prioritizes_relevant_globalids_not_first_alphabetic():
    unrelated=[wall(f"AAA{i:03}",100,["Generic 100 mm"]) for i in range(100)]
    related=wall("ZZZ-target",350,["Masonry existing (350 mm)"])
    elements=unrelated+[related]
    ranked=rank_element_requirement_candidates(elements,assembly(),max_pairs=80)
    chosen=select_graph_elements(elements,ranked,cap=40)
    assert len(chosen)==40
    assert chosen[0]["GlobalId"]=="ZZZ-target"
    assert len({e["GlobalId"] for e in chosen})==40


def test_explainable_graph_context_includes_pdf_page_globalid_and_uncertainty():
    e=wall("wall-one",350,["Masonry existing (350 mm)"])
    links=rank_element_requirement_candidates([e],assembly())
    graph=[{"globalId":"wall-one","storeys":["L2"],"materials":["Masonry existing"]}]
    rendered=format_grounded_link_context(links,graph)
    assert "PDF p.14" in rendered and "GlobalId=wall-one" in rendered
    assert "graph_storeys=['L2']" in rendered
    assert "NOT a compliance verdict" in rendered


def test_internal_wall_is_not_silently_eligible():
    e=wall("internal",350,["Brick (102 mm)","Cavity (150 mm)","Block (100 mm)"],external=False)
    l=rank_element_requirement_candidates([e],assembly())[0]
    assert l["ScreeningStatus"]=="SCOPE_CONFLICT"
    assert l["ComplianceVerdict"]=="NOT_ASSESSABLE"


def test_assembly_like_material_still_requires_reviewer():
    e=wall("possible",352,["Brick (102 mm)","Cavity (150 mm)","Block (100 mm)"])
    l=rank_element_requirement_candidates([e],assembly())[0]
    assert l["ScreeningStatus"]=="REVIEW_REQUIRED"
    assert l["StructuralComparability"]=="NOT_VERIFIED"


def test_result8_distant_elements_are_not_falsely_included():
    """Test 8 included 50-mm walls 302 mm from the 352-mm assembly."""
    source = [wall(f"close-{i}", 350 if i < 6 else 350.04375,
                   [f"Single masonry layer ({350 if i < 6 else 350.04375} mm)"])
              for i in range(13)]
    source += [wall(f"irrelevant-{i}", thickness, ["Generic concrete wall"])
               for i, thickness in enumerate((50, 100, 150, 250, 300, 330))]
    reqs = assembly()*3
    links = rank_element_requirement_candidates(source, reqs, max_pairs=80)
    assert len(links) == 39  # 13 plausible × three source clauses
    assert len({x["GlobalId"] for x in links}) == 13
    assert all(x["AbsNumericDifference_mm"] <= 15 for x in links)
    assert all(x["ComplianceVerdict"]=="NOT_ASSESSABLE" for x in links)
    assert all(x["RetrievalBasis"]=="numeric_proximity" for x in links)


def test_candidate_budget_is_distributed_across_distinct_clauses():
    a = assembly()[0]
    b = dict(a, PDFPage=15)
    c = dict(a, PDFPage=16)
    values = [wall(f"near-{i}",350,["Existing masonry"]) for i in range(12)]
    links=rank_element_requirement_candidates(values,[a,b,c],max_pairs=9)
    assert len(links)==9
    assert [sum(x["PDFPage"]==page for x in links) for page in (14,15,16)] == [3,3,3]


def test_material_assembly_evidence_can_keep_distant_property_but_not_verdict():
    e=wall("layered",420,["Brick (102 mm)","Cavity (150 mm)","Block (100 mm)"])
    p=rank_element_requirement_candidates([e],assembly())
    assert len(p)==1
    assert p[0]["RetrievalBasis"]=="material_assembly_terms"
    assert p[0]["ScreeningStatus"]=="REVIEW_REQUIRED"
    assert p[0]["ComplianceVerdict"]=="NOT_ASSESSABLE"
