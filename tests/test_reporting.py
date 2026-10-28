"""HTML report export checks."""
from reporting import colour_report_html

def test_report_escapes_ifc_and_pdf_text():
    result = colour_report_html([{
        "GlobalId": "x<y", "ElementName": "<b>untrusted</b>",
        "IssueCategory": "GEOMETRY_MISMATCH",
        "ReviewPriority": "Medium", "EvidenceReference": "PDF p. 12 < 13",
    }])
    assert "&lt;b&gt;untrusted&lt;/b&gt;" in result
    assert "PDF p. 12 &lt; 13" in result
    assert "#ffe2c2" in result
    assert "not structural or life-safety ratings" in result

def test_empty_report_valid():
    data=colour_report_html([])
    assert "No audit records" in data
    assert "Records:</b> 0" in data
