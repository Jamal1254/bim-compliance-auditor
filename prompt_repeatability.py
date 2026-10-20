"""Repeatability experiment evidence; similarity is NOT compliance accuracy."""
import hashlib
import re
from collections import defaultdict

PAGE_RE=re.compile(r"(?:\[\s*PDF\s*page\s*|\bPDF\s*page\s*:?\s*|\bpage\s*:?\s*)(\d{1,4})",re.I)
GUID_RE=re.compile(r"(?<![A-Za-z0-9_$])[A-Za-z0-9_$]{22}(?![A-Za-z0-9_$])")

def record_output(variant,repeat,model_requested,model_used,prompt_hash,text,source_pages=None,error=""):
    pages=sorted({int(x) for x in PAGE_RE.findall(text)})
    valid=set(source_pages or [])
    return {"prompt_variant":variant,"repeat":repeat,"model_requested":model_requested,
            "model_used":model_used,"prompt_sha256":prompt_hash,
            "response_sha256":hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "pages_cited":pages,
            "citations_not_in_pdf":sorted(set(pages)-valid) if source_pages else [],
            "global_ids_cited":sorted(set(GUID_RE.findall(text))),
            "response_text":text,"provider_error":error}

def summarise_repeats(records):
    grouped=defaultdict(list)
    for r in records:grouped[r["prompt_variant"]].append(r)
    out={}
    for variant,items in grouped.items():
        valid=[r for r in items if not r.get("provider_error")]
        hashes={r["response_sha256"] for r in valid}
        page_sets=[set(r["pages_cited"]) for r in valid]
        similarities=[]
        for i in range(len(page_sets)):
            for j in range(i+1,len(page_sets)):
                union=page_sets[i]|page_sets[j]
                # No citations in either response is MISSING EVIDENCE, not perfect overlap.
                if union:
                    similarities.append(len(page_sets[i] & page_sets[j]) / len(union))
        models = {r.get("model_used") for r in valid if r.get("model_used")}
        cited_runs = sum(bool(pages) for pages in page_sets)
        out[variant]={"attempted":len(items),"successful":len(valid),
                      "distinct_responses":len(hashes),
                      "identical_text_across_repeats":len(valid)>1 and len(hashes)==1,
                      "models_used":sorted(models),
                      "same_model_across_repeats":len(valid)>1 and len(models)==1,
                      "runs_with_page_citations":cited_runs,
                      "mean_page_citation_jaccard":round(sum(similarities)/len(similarities),4) if similarities else None,
                      "citation_similarity_interpretable":bool(similarities),
                      "unsupported_page_citations":sum(len(r["citations_not_in_pdf"]) for r in valid)}
    return out
