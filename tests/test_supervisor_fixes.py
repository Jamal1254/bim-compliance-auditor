import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from audit_engine import AuditRule, audit_elements, categories_summary
from validation import evaluate_records, seeded_type_sample


def _element(gid, thickness, materials=None, is_external=True):
    return {"GlobalId": gid, "Type": "IfcWall", "Name": "External Wall",
            "Width": thickness, "Materials": materials or [], "IsExternal": is_external}


def test_deliberate_difference_350_4_vs_352_detected():
    results = audit_elements([_element("A", 350.4), _element("B", 352)],
                             AuditRule(thickness_mm=352, scope="all"))
    assert [r["IssueCategory"] for r in results] == ["GEOMETRY_MISMATCH", "PASS"]
    assert results[0]["ThicknessDifference_mm"] == -1.6


def test_per_element_not_hidden_by_category():
    w = [_element("A", 350.4), _element("B", 352)]
    r = audit_elements(w, AuditRule(thickness_mm=352, scope="all"))
    assert len(r) == 2 and {x["GlobalId"] for x in r} == {"A", "B"}


def test_missing_data_and_scope():
    w = [_element("A", None, [], True), _element("B", 352, ["Brick"], None)]
    rule = AuditRule(thickness_mm=352, required_materials=("Brick",), scope="external")
    r = audit_elements(w, rule)
    assert r[0]["IssueCategory"] == "MISSING_BOTH"
    assert r[1]["IssueCategory"] == "NOT_APPLICABLE"


def test_evaluation_metrics():
    records = [
        {"predicted_mismatch":"1","ground_truth_mismatch":"1"},
        {"predicted_mismatch":"1","ground_truth_mismatch":"0"},
        {"predicted_mismatch":"0","ground_truth_mismatch":"1"},
        {"predicted_mismatch":"0","ground_truth_mismatch":"0"},
        {"predicted_mismatch":"","ground_truth_mismatch":"0"},
    ]
    stats = evaluate_records(records)
    assert [stats[x] for x in ["TP","FP","FN","TN","N_excluded"]] == [1,1,1,1,1]
    assert stats["F1"] == 0.5


def test_reproducible_sample():
    rows = [{"GlobalId":str(i),"Type": "IfcWall"} for i in range(20)]
    assert seeded_type_sample(rows, {"IfcWall": 5}, seed=99) == seeded_type_sample(rows, {"IfcWall": 5}, seed=99)
