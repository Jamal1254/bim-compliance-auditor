"""Human-reviewed, element-specific retrieval validation.

No model output may write into a ground-truth column. This tests the top
suggested (element, clause) pair for each sampled IFC element. It is NOT a
global recall estimate across all clauses in the specification.
"""
from collections import defaultdict
from validation import evaluate_records

YES={"1","yes","y","true"}
NO={"0","no","n","false"}


def _binary(v):
    s=str(v or "").strip().lower()
    if s in YES:
        return "1"
    if s in NO:
        return "0"
    return ""


def link_review_worksheet(sample_rows, ranked_links):
    """Attach one top source candidate per element, never pre-fill human truth."""
    first={}
    for pair in ranked_links:
        first.setdefault(str(pair.get("GlobalId") or ""),pair)
    out=[]
    for row in sample_rows:
        gid=str(row.get("GlobalId") or "")
        candidate=first.get(gid)
        out.append({
            "GlobalId":gid, "SampleIFCType":row.get("IFCType",row.get("SampleIFCType","")),
            "ElementName":row.get("ElementName",row.get("SampleName","")),
            "ObservedThickness_mm":row.get("ObservedThickness_mm",""),
            "PredictedTopCandidate": "1" if candidate else "0",
            "CandidateRequirementID": candidate["RequirementID"] if candidate else "",
            "CandidatePDFPage": candidate["PDFPage"] if candidate else "",
            "CandidateClauseText": candidate["ClauseText"] if candidate else "",
            "CandidateIFCMaterials": candidate["IFCMaterials"] if candidate else "",
            "CandidateReasons": candidate["Reasons"] if candidate else "",
            "CandidateStatus": candidate["ScreeningStatus"] if candidate else "NO_CANDIDATE",
            "verified_document_applies": "",  # independent reviewer ONLY
            "ground_truth_top_candidate_relevant": "",
            "ground_truth_property_comparable": "",
            "ground_truth_mismatch": "",
            "reviewer_notes": "",
        })
    return out


def evaluate_link_review(rows):
    """TP/FP/TN/FN for top-1 candidate retrieval with explicit abstentions.

    Only reviewer-confirmed document applicability and binary independent
    top-candidate truth are eligible. A wrong or absent contract excludes a
    case rather than becoming a true negative without careful annotation.
    """
    all_rows=list(rows)
    records=[]
    categories=defaultdict(list)
    missing_document=0
    missing_truth=0
    for r in all_rows:
        if _binary(r.get("verified_document_applies",""))!="1":
            missing_document+=1
            continue
        truth=_binary(r.get("ground_truth_top_candidate_relevant",""))
        if not truth:
            missing_truth+=1
            continue
        mapped={"predicted_mismatch":_binary(r.get("PredictedTopCandidate","")),
                "ground_truth_mismatch":truth}
        records.append(mapped)
        categories[str(r.get("SampleIFCType") or "UNKNOWN")].append(mapped)
    summary=evaluate_records(records)
    summary["N_total_sampled"]=len(all_rows)
    summary["N_document_not_verified"]=missing_document
    summary["N_ground_truth_unlabelled"]=missing_truth
    summary["metric_scope"]="top-1 candidate retrieval on reviewer-verified cases; NOT contract-compliance F1"
    summary["by_IFC_type"]={name:evaluate_records(items) for name,items in sorted(categories.items())}
    return summary
