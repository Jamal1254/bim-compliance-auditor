"""Evidence discovery in *any uploaded* digitally searchable PDF.

Text fragments are candidates, not contract rules. No numeric requirement is
coded into this retriever. Uses 1-based PDF page indices including cover.
"""
from io import BytesIO
import re
from pypdf import PdfReader

CATEGORY_TERMS = {
    "wall": ("wall", "masonry", "brick", "blockwork", "partition", "cavity", "cladding"),
    "beam": ("beam", "girder", "joist", "lintel", "structural steel"),
    "slab": ("slab", "floor", "concrete deck", "reinforcement"),
    "column": ("column", "pillar", "post"),
    "door": ("door", "entrance", "doorway", "fire door"),
    "window": ("window", "glazing", "fenestration"),
    "roof": ("roof", "roofing"),
    "footing": ("footing", "foundation", "pile cap"),
    "pile": ("pile", "foundation"),
    "stair": ("stair", "staircase", "riser", "tread"),
    "pipe": ("pipe", "plumbing", "service"),
    "duct": ("duct", "ventilation", "hvac"),
    "member": ("member", "structural"),
}


def _types(component):
    if isinstance(component, (list, tuple, set)):
        raw = list(component)
    else:
        raw = str(component or "").split(",")
    kinds = [str(x).replace("Ifc", "").replace("StandardCase", "").strip().casefold() for x in raw]
    kinds = [x for x in kinds if x and x not in {"all model elements", "all", "all sample types", "*"}]
    return list(dict.fromkeys(kinds)) or ["wall", "beam", "slab", "column", "door", "window"]


def _sentences(page_text):
    lines = [re.sub(r"\s+", " ", t).strip() for t in page_text.splitlines() if t.strip()]
    # Adjacent PDF lines usually belong to the same clause. Provide neighbouring
    # text rather than disconnected single-line numbers.
    out = []
    for i in range(0, len(lines), 3):
        fragment = " ".join(lines[i:i+3])[:1400]
        if len(fragment) >= 35:
            out.append(fragment)
    return out


def clause_candidates(pdf_bytes, component="Wall", max_chars=16000):
    reader = PdfReader(BytesIO(pdf_bytes))
    types = _types(component)
    concepts = {t: CATEGORY_TERMS.get(t, (t,)) for t in types}
    candidates = []
    fallback_fragments = []  # For searchable non-English PDFs with no English class tokens.
    page_chars = 0
    for i, page in enumerate(reader.pages, 1):
        txt = page.extract_text() or ""
        page_chars += len(txt.strip())
        for frag in _sentences(txt):
            if len(fallback_fragments) < 120:
                fallback_fragments.append({"Page":i,"Score":0,"Text":frag,"Types":["unmatched-language-review"]})
            low = frag.casefold()
            matched = [t for t, words in concepts.items() if any(w in low for w in words)]
            if not matched:
                continue
            numeric = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m\b|inches?|feet|ft\b|kN|MPa|N/mm|W/m|%|hr|hours?)", low))
            score = 10 * len(matched) + (3 if numeric else 0)
            candidates.append({"Page": i, "Score": score, "Text": frag, "Types": matched})
    if page_chars == 0:
        raise ValueError("The PDF has no extractable text. Upload a text-searchable/OCR-processed specification.")
    if not candidates:
        # International documents may be searchable yet have no English class
        # terms. Pass low-confidence page-grounded text for optional review.
        # Never treat this fallback as a verified match.
        candidates = fallback_fragments
    # Fair sampling across element types prevents one category from monopolising
    # the LLM context, e.g. walls drowning out doors and beams.
    selected, used_ids, budget = [], set(), 0
    for typ in types:
        per_type = sorted(enumerate(candidates), key=lambda x: (-x[1]["Score"], x[1]["Page"]))
        count = 0
        for i, item in per_type:
            if typ not in item["Types"] or i in used_ids:
                continue
            cost = len(item["Text"]) + 55
            if budget + cost > max_chars:
                continue
            selected.append(item); used_ids.add(i); budget += cost; count += 1
            if count >= 3:
                break
    for i, item in sorted(enumerate(candidates), key=lambda x:(-x[1]["Score"],x[1]["Page"])):
        if i in used_ids:
            continue
        cost = len(item["Text"]) + 55
        if budget + cost <= max_chars:
            selected.append(item); budget += cost
    return sorted(selected, key=lambda x:(x["Page"],-x["Score"])),len(candidates)


def candidates_text(candidates):
    return "\n\n".join(f"[PDF page {x['Page']}; candidates: {', '.join(x['Types'])}] {x['Text']}" for x in candidates)
