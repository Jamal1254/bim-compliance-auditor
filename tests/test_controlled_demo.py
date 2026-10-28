"""Synthetic classifier fixture must exercise full report legend, not invent accuracy."""
from controlled_demo import synthetic_classification_examples
from audit_engine import categories_summary
from reporting import colour_report_html

def test_all_supervisor_categories_present_and_labelled_synthetic():
    rows=synthetic_classification_examples()
    c=categories_summary(rows)
    assert set(c)=={
        "PASS","GEOMETRY_MISMATCH","MATERIAL_MISMATCH","MISMATCH_BOTH",
        "MISSING_GEOMETRY","MISSING_MATERIAL","MISSING_BOTH","REVIEW_REQUIRED"}
    assert all(r["ComparisonMode"]=="CONTROLLED_TEST" for r in rows)
    assert all(r["GlobalId"].startswith("SYNTHETIC-") for r in rows)
    assert all("NOT A HUMAN-LABELLED" in r["ResearchGroundTruth"] for r in rows)
    html=colour_report_html(rows,title="SYNTHETIC EXAMPLE ONLY")
    assert "SYNTHETIC" in html and "GEOMETRY_MISMATCH" in html
