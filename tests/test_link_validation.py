"""Ground truth cannot be inferred from model predictions or source keywords."""
from link_validation import link_review_worksheet,evaluate_link_review

def sample(gid,typ="IfcWall"):
    return {"GlobalId":gid,"IFCType":typ,"ElementName":gid,
            "ObservedThickness_mm":350}

def pair(gid):
    return {"GlobalId":gid,"RequirementID":"PDF-P14-A1","PDFPage":14,
            "ClauseText":"352mm cavity wall construction","IFCMaterials":"Masonry",
            "Reasons":"Geometry proximity only","ScreeningStatus":"ASSEMBLY_NOT_ESTABLISHED"}

def test_worksheet_does_not_fabricate_human_annotations():
    data=link_review_worksheet([sample("a"),sample("b","IfcDoor")],[pair("a")])
    assert len(data)==2
    assert data[0]["PredictedTopCandidate"]=="1"
    assert data[1]["PredictedTopCandidate"]=="0"
    for row in data:
        assert row["verified_document_applies"]==""
        assert row["ground_truth_top_candidate_relevant"]==""
        assert row["ground_truth_mismatch"]==""

def test_no_ground_truth_means_no_precision():
    data=link_review_worksheet([sample("a")],[pair("a")])
    report=evaluate_link_review(data)
    assert report["N_evaluated"]==0
    assert report["N_document_not_verified"]==1
    assert report["precision"] is None and report["F1"] is None

def test_annotated_metrics_and_exclusions_by_type():
    rows=link_review_worksheet([sample("tp"),sample("fp"),sample("tn","IfcDoor"),
                                sample("fn","IfcDoor"),sample("unknown")],
                               [pair("tp"),pair("fp"),pair("unknown")])
    truths={"tp":"1","fp":"0","tn":"0","fn":"1"}
    for row in rows:
        if row["GlobalId"] in truths:
            row["verified_document_applies"]="yes"
            row["ground_truth_top_candidate_relevant"]=truths[row["GlobalId"]]
    result=evaluate_link_review(rows)
    assert (result["TP"],result["FP"],result["TN"],result["FN"])==(1,1,1,1)
    assert result["N_evaluated"]==4
    assert result["N_document_not_verified"]==1
    assert result["by_IFC_type"]["IfcWall"]["FP"]==1
    assert result["by_IFC_type"]["IfcDoor"]["FN"]==1
    assert result["F1"]==0.5

def test_unverified_document_excluded_not_false_negative():
    rows=link_review_worksheet([sample("a")],[])
    rows[0]["ground_truth_top_candidate_relevant"]="yes"
    r=evaluate_link_review(rows)
    assert r["N_evaluated"]==0 and r["N_document_not_verified"]==1
