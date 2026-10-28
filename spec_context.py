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


def adjacent_pdf_context(pdf_bytes, page_number, radius=2, per_page_limit=6500):
    """Read the original and adjacent PDF pages, preserving 1-based page numbers.

    This is for human scope verification, not an automatic contract match.
    A paragraph can depend on limitations on earlier pages.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    page_number = int(page_number)
    if page_number < 1 or page_number > len(reader.pages):
        raise ValueError("PDF page is outside the uploaded document.")
    radius = max(0, min(3, int(radius)))
    sections = []
    for index in range(max(0, page_number - radius - 1),
                       min(len(reader.pages), page_number + radius)):
        text = (reader.pages[index].extract_text() or "").strip()
        sections.append(f"PDF page {index+1} (1-based upload page)\n"
                        + (text[:per_page_limit] if text else "[No extractable text]"))
    return "\n\n========== NEXT PAGE ==========\n\n".join(sections)


_ASSEMBLY_REGEX = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:[.,]\d+)?)\s*mm\s+"
    r"(?P<kind>cavity\s+wall\s+construction|facing\s+masonry)\b",
    re.IGNORECASE,
)


def find_wall_assembly_specifications(pdf_bytes, max_results=60):
    """Find explicit assembly-level specifications across the entire PDF.

    Return source pages and contextual lines. These are unverified clauses,
    NOT rules applicable to individual IFC elements. A specified masonry
    assembly is not automatically comparable to a single IFC material layer.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    results = []
    for page_index, page in enumerate(reader.pages, 1):
        lines = [re.sub(r"\s+", " ", line).strip()
                 for line in (page.extract_text() or "").splitlines()]
        lines = [line for line in lines if line]
        for line_index, line in enumerate(lines):
            match = _ASSEMBLY_REGEX.search(line)
            if match is None:
                continue
            value = float(match.group("value").replace(",", "."))
            if not 0 < value <= 2000:
                continue
            start = max(0, line_index - 8)
            finish = min(len(lines), line_index + 7)
            evidence = " ".join(lines[start:finish])
            results.append({
                "PDFPage": page_index,
                "AssemblyThickness_mm": value,
                "AssemblyKind": match.group("kind").lower(),
                "QuotedLine": line,
                "SurroundingText": evidence[:2600],
                "ComparisonMeaning": "NOMINAL_ASSEMBLY_NOT_AUTOMATIC_MINIMUM",
                "ContractualApplicability": "NOT_VERIFIED",
                "IFCElementLink": "NOT_VERIFIED",
            })
            if len(results) >= max_results:
                return results
    return results
