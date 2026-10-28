"""Check original PDF page retrieval without invoking any model or database."""
from spec_context import adjacent_pdf_context
import spec_context
import pytest

def test_adjacent_pdf_context_one_based_pages(monkeypatch):
    class Page:
        def __init__(self, n): self.n=n
        def extract_text(self): return f"Page {self.n} content from the PDF"
    class Reader:
        def __init__(self, _): self.pages=[Page(i) for i in range(1,8)]
    monkeypatch.setattr(spec_context, "PdfReader", Reader)
    excerpt=adjacent_pdf_context(b"pdf-mock", page_number=4, radius=2)
    assert "PDF page 2" in excerpt and "PDF page 6" in excerpt
    assert "PDF page 1" not in excerpt and "PDF page 7" not in excerpt
    assert "Page 4 content" in excerpt

def test_adjacent_context_validates_page_and_bounds(monkeypatch):
    class Page:
        def extract_text(self): return "test"
    class Reader:
        def __init__(self, _): self.pages=[Page(), Page()]
    monkeypatch.setattr(spec_context, "PdfReader", Reader)
    assert "PDF page 1" in adjacent_pdf_context(b"pdf", 1, radius=3)
    assert "PDF page 2" in adjacent_pdf_context(b"pdf", 1, radius=3)
    with pytest.raises(ValueError,match="outside"):
        adjacent_pdf_context(b"pdf", 3)
