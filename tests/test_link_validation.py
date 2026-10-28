"""Ground truth cannot be inferred from ranked source/element candidates."""
import pytest
from link_validation import (
    link_review_worksheet, evaluate_link_review, wall_validation_sample,
    validate_frozen_review_rows,
)


def sample(gid, typ="IfcWall", width=350):
    return {"GlobalId":gid, "IFCType":typ,"ElementName":gid,
            "ObservedThickness_mm":width}


def pair(gid, req="PDF-P14-A1"):
    return {"GlobalId":gid, "RequirementID":req,"PDFPage":14,
            "ClauseText":"352mm cavity wall construction",
            "IFCMaterials":"Masonry","Reasons":"Geometry proximity only",
            "ScreeningStatus":"ASSEMBLY_NOT_ESTABLISHED"}


def test_worksheet_does_not_fabricate_truth_or_evaluate_nonwall_as_negative():
    rows=link_review_worksheet([sample("a"), sample("b","IfcDoor")], [pair("a")])
    assert rows[0]["EvaluationEligible"]=="YES"
    assert rows[0]["PredictedTopCandidate"]=="1"
    assert rows[1]["EvaluationEligible"]=="NO"
    assert rows[1]["CandidateStatus"]=="CLASS_OUTSIDE_WALL_RETRIEVER"
    assert all(r["ground_truth_applicable_requirement_ids"]=="" for r in rows)
    summary=evaluate_link_review(rows)
    assert summary["N_evaluated"]==0
    assert summary["N_unsupported_IFC_class"]==1
    assert summary["N_document_not_verified"]==1
    assert summary["F1"] is None


def test_true_wrong_missing_and_negative_link_event_counts():
    rows=link_review_worksheet([
        sample("tp"),sample("fp"),sample("tn"),
        sample("fn"),sample("wrong"),sample("notverified")
    ], [pair("tp"),pair("fp"),pair("wrong"),pair("notverified")])
    labels={"tp":"PDF-P14-A1","fp":"NONE","tn":"NONE",
            "fn":"PDF-P14-A1","wrong":"PDF-P15-A2"}
    for r in rows:
        if r["GlobalId"] in labels:
            r["verified_document_applies"]="yes"
            r["ground_truth_applicable_requirement_ids"]=labels[r["GlobalId"]]
    result=evaluate_link_review(rows)
    assert (result["TP"],result["FP"],result["TN"],result["FN"])==(1,2,1,2)
    assert result["N_wrong_candidate_and_missed_true_link"]==1
    assert result["N_evaluated"]==5
    assert result["N_document_not_verified"]==1
    assert result["precision"]==pytest.approx(1/3)
    assert result["recall"]==pytest.approx(1/3)
    assert result["F1"]==pytest.approx(1/3)


def test_wall_sample_balances_linked_and_unlinked_reproducibly():
    pool=[sample(f"wall-{i:03}") for i in range(100)]
    ranked=[pair(f"wall-{i:03}") for i in range(13)]
    a=wall_validation_sample(pool,ranked,n=30,seed=2026)
    b=wall_validation_sample(list(reversed(pool)),ranked,n=30,seed=2026)
    assert [r["GlobalId"] for r in a]==[r["GlobalId"] for r in b]
    assert len(a)==30
    assert sum(r["SamplingStratum"]=="RETRIEVED_PAIR" for r in a)==13
    assert sum(r["SamplingStratum"]=="NO_RETRIEVED_PAIR" for r in a)==17
    assert len(set(r["GlobalId"] for r in a))==30


def test_review_fields_are_editable_but_source_and_predictions_immutable():
    original=link_review_worksheet([sample("a")],[pair("a")])
    valid=[dict(original[0])]
    valid[0]["verified_document_applies"]="yes"
    valid[0]["ground_truth_applicable_requirement_ids"]="PDF-P14-A1"
    assert validate_frozen_review_rows(original, valid) is True
    altered=[dict(valid[0],CandidateRequirementID="PDF-P14-A2")]
    with pytest.raises(ValueError,match="Frozen evidence"):
        validate_frozen_review_rows(original,altered)
    changed=[dict(valid[0],PredictedTopCandidate="0")]
    with pytest.raises(ValueError,match="Frozen evidence"):
        validate_frozen_review_rows(original,changed)
    with pytest.raises(ValueError,match="Duplicate"):
        validate_frozen_review_rows([*original,dict(original[0],GlobalId="b")],
                                    [valid[0],dict(valid[0])])


def test_invalid_truth_and_nonapplicable_project_excluded():
    rows=link_review_worksheet([sample("a"),sample("b")],[pair("a")])
    rows[0]["verified_document_applies"]="yes"
    rows[0]["ground_truth_applicable_requirement_ids"]="MAYBE"
    rows[1]["verified_document_applies"]="no"
    rows[1]["ground_truth_applicable_requirement_ids"]="NONE"
    score=evaluate_link_review(rows)
    assert score["N_evaluated"]==0
    assert score["N_ground_truth_unlabelled"]==1
    assert score["N_document_not_verified"]==1
