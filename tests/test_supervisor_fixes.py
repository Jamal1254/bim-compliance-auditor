import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_engine import AuditRule, audit_elements, categories_summary
from validation import evaluate_records, seeded_type_sample
from spec_context import clause_candidates
from pypdf import PdfWriter
from io import BytesIO


def _wall(gid, width, materials=None, external=True, src="Sum of IFC material layers"):
    return {"GlobalId": gid, "Type": "IfcWall", "Name": "External Wall",
            "Width": width, "Materials": materials or [], "IsExternal": external,
            "WidthSource": src}


def rule(**kwargs):
    return AuditRule(thickness_mm=352, scope="all", source="Synthetic 352 mm controlled test", **kwargs)


def test_no_rule_no_pass_fail_even_with_known_width():
    result = audit_elements([_wall("A", 352), _wall("B", None)], None)
    assert all(x["IssueCategory"] == "NOT_ASSESSABLE" for x in result)
    assert all(x["ComparisonMode"] == "UNVERIFIED" for x in result)


def test_deliberate_mismatch_and_individual_ids():
    result = audit_elements([_wall("A", 350.4), _wall("B", 352)], rule())
    assert [(r["GlobalId"], r["IssueCategory"]) for r in result] == [
        ("A", "GEOMETRY_MISMATCH"), ("B", "PASS")]
    assert result[0]["ThicknessDifference_mm"] == -1.6
    assert all(r["ComparisonMode"] == "CONTROLLED_TEST" for r in result)


def test_unknown_scope_is_never_a_pass():
    r = audit_elements([_wall("C", 352, external=None)],
                       AuditRule(thickness_mm=352, scope="external", source="p.14", test_mode=False))
    assert r[0]["IssueCategory"] == "SCOPE_UNVERIFIED"


def test_name_and_material_checks():
    r = audit_elements([_wall("A", 352, ["Plasterboard"])],
                       rule(required_materials=("Brick",)))
    assert r[0]["IssueCategory"] == "MATERIAL_MISMATCH"


def test_missing_dimension_not_a_false_compliance_verdict():
    r = audit_elements([_wall("A", None)], rule())
    assert r[0]["IssueCategory"] == "MISSING_GEOMETRY"


def test_approximate_geometry_requires_review():
    r = audit_elements([_wall("A", 352, src="Axis-aligned 3D bounding-box (approximate)")], rule())
    assert r[0]["IssueCategory"] == "REVIEW_REQUIRED"


def test_no_all_elements_verified_rule():
    try:
        AuditRule(thickness_mm=352, scope="all", test_mode=False, source="p.14")
    except ValueError as e:
        assert "controlled test" in str(e)
    else:
        raise AssertionError("Must prohibit universal contractual rules")


def test_missing_reference_rejected():
    try:
        AuditRule(thickness_mm=352, source="")
    except ValueError:
        pass
    else:
        raise AssertionError("Must require a recorded test or specification source")


def test_metrics():
    data = [
        {"predicted_mismatch": "1", "ground_truth_mismatch": "1"},
        {"predicted_mismatch": "1", "ground_truth_mismatch": "0"},
        {"predicted_mismatch": "0", "ground_truth_mismatch": "1"},
        {"predicted_mismatch": "0", "ground_truth_mismatch": "0"},
        {"predicted_mismatch": "", "ground_truth_mismatch": "0"},
    ]
    stat = evaluate_records(data)
    assert [stat[x] for x in ("TP", "FP", "FN", "TN", "N_excluded")] == [1, 1, 1, 1, 1]
    assert stat["F1"] == 0.5


def test_reproducible_sample():
    items = [{"GlobalId": str(i), "Type": "IfcWall"} for i in range(20)]
    assert seeded_type_sample(items, {"IfcWall": 5}, seed=99) == seeded_type_sample(items, {"IfcWall": 5}, seed=99)


def test_spec_context_preserves_pdf_page_numbers():
    # pypdf-generated blank pages do not have searchable text.
    # Exercise empty PDFs and ensure this does not silently hallucinate clauses.
    w = PdfWriter(); w.add_blank_page(width=250, height=350)
    buf = BytesIO(); w.write(buf)
    records, count = clause_candidates(buf.getvalue(), "Wall")
    assert records == [] and count == 0
