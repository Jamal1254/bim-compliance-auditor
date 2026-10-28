"""Check original PDF page retrieval without invoking any model or database."""
from spec_context import adjacent_pdf_context, find_wall_assembly_specifications
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


def test_find_nominal_352_assembly_without_confusing_90mm_leaf(monkeypatch):
    class Page:
        def __init__(self, text): self.text=text
        def extract_text(self): return self.text
    class Reader:
        def __init__(self, _):
            self.pages=[
                Page("Foundations\n250mm depth."),
                Page("External Masonry Walls\nWalls below damp proof course\n"
                     "2 Storey Houses\n"
                     "352mm cavity wall construction for a minimum of 3 courses below dpc level comprising\n"
                     "102mm outer leaf brickwork. 150mm cavity. 100mm inner blockwork.\n"
                     "352mm Facing masonry applicable to all storey heights comprising:\n"
                     "102mm brickwork. 150mm cavity. 100mm blockwork."),
                Page("All cavity walls should have leaves at least 90mm thick and cavities at least 50mm wide.")
            ]
    monkeypatch.setattr(spec_context, "PdfReader", Reader)
    found = find_wall_assembly_specifications(b"pdf")
    assert len(found) == 2
    assert [x["PDFPage"] for x in found] == [2, 2]
    assert [x["AssemblyThickness_mm"] for x in found] == [352.0,352.0]
    assert all(x["IFCElementLink"] == "NOT_VERIFIED" for x in found)
    assert all(x["ComparisonMeaning"] == "NOMINAL_ASSEMBLY_NOT_AUTOMATIC_MINIMUM" for x in found)
    assert all("90mm" not in x["QuotedLine"] for x in found)


def test_wall_assembly_discovery_is_not_limited_to_dorchester_phrases(monkeypatch):
    class Page:
        def __init__(self, text): self.text=text
        def extract_text(self): return self.text
    class Reader:
        def __init__(self, _):
            self.pages=[Page(
                "External wall construction: 300mm external wall construction.\n"
                "Concrete wall assembly 250mm concrete wall assembly.\n"
                "Partition design: 125mm partition.\n"
                "Layer rule: 100mm insulation layer."
            )]
    monkeypatch.setattr(spec_context, "PdfReader", Reader)
    found = find_wall_assembly_specifications(b"pdf")
    assert [x["AssemblyThickness_mm"] for x in found] == [300.0, 250.0, 125.0]
    assert all(x["IFCElementLink"] == "NOT_VERIFIED" for x in found)
