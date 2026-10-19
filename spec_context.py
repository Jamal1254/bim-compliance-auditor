"""Extract page-referenced, topical *candidate* clauses from construction PDFs.

A candidate clause is NOT established project ground truth: applicability must
be independently verified. PDF pages are 1-indexed (including front matter).
"""
from io import BytesIO
from pypdf import PdfReader

WALL_TERMS = ("wall", "masonry", "cavity", "brickwork", "blockwork", "partition", "render", "insulation", "thickness")


def clause_candidates(pdf_bytes, component="Wall", max_chars=14000):
    reader = PdfReader(BytesIO(pdf_bytes))
    kind = (component or "Wall").strip().lower()
    if "wall" in kind:
        words = WALL_TERMS
    else:
        words = (kind, "thickness", "material", "fire rating", "strength", "depth", "width")
    fragments = []
    for number, page in enumerate(reader.pages, 1):
        body = page.extract_text() or ""
        paras = [x.strip().replace("\n", " ") for x in body.split("\n\n") if len(x.strip()) > 40]
        if len(paras) < 2:
            paras = [x.strip() for x in body.split("\n") if len(x.strip()) > 40]
        for para in paras:
            low = para.casefold()
            relevant = [t for t in words if t in low]
            if not relevant:
                continue
            score = len(relevant) * 2 + 4 * (kind in low)
            if kind == "wall":
                score += 3 * ("cavity" in low) + 3 * ("external" in low and "wall" in low)
            fragments.append({"Page": number, "Score": score, "Text": para[:1600]})
    fragments.sort(key=lambda x: (-x["Score"], x["Page"], x["Text"]))
    chosen = []
    used = 0
    for record in fragments:
        size = len(record["Text"]) + 36
        if used + size > max_chars:
            continue
        chosen.append(record)
        used += size
    chosen.sort(key=lambda x: (x["Page"], -x["Score"]))
    return chosen, len(fragments)


def candidates_text(candidates):
    return "\n\n".join(f"[PDF page {x['Page']}] {x['Text']}" for x in candidates)
