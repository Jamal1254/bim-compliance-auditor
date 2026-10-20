"""Supervisor category, element-linkage and prompt repeatability checks."""
from audit_engine import AuditRule,audit_elements
import evidence_linking
from prompt_repeatability import record_output,summarise_repeats

def test_six_observation_categories():
    cases=[
        ("PASS",100,["Concrete"],100),
        ("GEOMETRY_MISMATCH",110,["Concrete"],100),
        ("MATERIAL_MISMATCH",100,["Wood"],100),
        ("MISSING_GEOMETRY",None,["Concrete"],100),
        ("MISSING_MATERIAL",100,[],100),
        ("MISSING_BOTH",None,[],100)]
    for i,(expected,width,materials,target) in enumerate(cases):
        gid=f"synthetic-{i}"
        elem={"GlobalId":gid,"Type":"IfcWallStandardCase","Name":"test wall",
              "Width":width,"Materials":materials,"WidthSource":"IFC layer",
              "IsExternal":True}
        rule=AuditRule(thickness_mm=target,tolerance_mm=0.5,scope="global_id",
                       global_id=gid,required_materials=("Concrete",),
                       source="SYNTHETIC-TEST",test_mode=True)
        output=audit_elements([elem],rule)[0]
        assert output["IssueCategory"]==expected
        assert output["ComparisonMode"]=="CONTROLLED_TEST"
        assert output["ReviewPriority"] in {"High","Medium","None"}

def test_wrong_element_out_of_scope():
    wall={"GlobalId":"wall","Type":"IfcWall","Width":100,"Materials":["Concrete"]}
    door={"GlobalId":"door","Type":"IfcDoor","Width":100,"Materials":["Concrete"]}
    r=AuditRule(thickness_mm=100,scope="global_id",global_id="wall",source="TEST")
    assert audit_elements([door,wall],r)[0]["IssueCategory"]=="NOT_APPLICABLE"

def test_explicit_pdf_id_link(monkeypatch):
    gid="1TNtWJ3wP23fxn_QcLsoEm"
    class Page:
        def extract_text(self):
            return f"IfcWallStandardCase GlobalId {gid}\nRequired wall thickness: 352 mm"
    class Reader:
        pages=[Page()]
        def __init__(self,*args):pass
    monkeypatch.setattr(evidence_linking,"PdfReader",Reader)
    els=[{"GlobalId":gid,"Type":"IfcWallStandardCase"},
         {"GlobalId":"1TNtWJ3wP23fxn_QcLsoEb","Type":"IfcWallStandardCase"}]
    links=evidence_linking.link_pdf_evidence(b"PDF-fixture",els)
    assert len(links)==1 and links[0]["GlobalId"]==gid
    assert "352 mm" in links[0]["CandidateText"]
    assert links[0]["ComplianceVerdict"]=="NOT_ASSESSABLE"

def test_repeatability_citation_overlap():
    a=record_output("A",1,"model","model","hash","[PDF page 1] wall; [PDF page 2] beam",{1,2})
    b=record_output("A",2,"model","model","hash","[PDF page 1] wall; [PDF page 3] door",{1,2})
    summary=summarise_repeats([a,b])["A"]
    assert summary["mean_page_citation_jaccard"]==0.3333
    assert summary["unsupported_page_citations"]==1
    assert "precision" not in summary
