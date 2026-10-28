"""Independent assessment of source-to-IFC candidate retrieval.

A predicted candidate is never a human ground truth. This module measures
*element-to-requirement retrieval*, not building compliance or the quality of
all requirements in a PDF. Unrelated IFC classes must not inflate TN counts.
"""
import random
import re
from collections import defaultdict

SUPPORTED_CLASSES = {"IfcWall", "IfcWallStandardCase"}
YES = {"1", "yes", "y", "true"}
NO = {"0", "no", "n", "false"}


def _binary(value):
    s = str(value or "").strip().lower()
    if s in YES:
        return "1"
    if s in NO:
        return "0"
    return ""


def wall_validation_sample(observed_rows, ranked_links, n=30, seed=2026):
    """Reproducibly sample linked and unlinked walls for honest retrieval testing.

    An evidence-balanced cohort is deliberately NOT population-proportional.
    A separate random mixed-class sample may test class coverage, but cannot
    estimate wall retrieval recall if it contains almost no supported walls.
    """
    if n < 0:
        raise ValueError("Sample size must be nonnegative")
    unique = {}
    for r in observed_rows:
        gid = str(r.get("GlobalId") or "")
        if gid and str(r.get("IFCType") or "") in SUPPORTED_CLASSES:
            unique.setdefault(gid, dict(r))
    linked_ids = {str(r.get("GlobalId") or "") for r in ranked_links}
    linked = sorted((r for gid, r in unique.items() if gid in linked_ids),
                    key=lambda x: x["GlobalId"])
    unlinked = sorted((r for gid, r in unique.items() if gid not in linked_ids),
                      key=lambda x: x["GlobalId"])
    rng = random.Random(seed)
    rng.shuffle(linked)
    rng.shuffle(unlinked)
    total = min(n, len(linked) + len(unlinked))
    linked_target = min(len(linked), (total + 1) // 2)
    unlinked_target = min(len(unlinked), total - linked_target)
    chosen = linked[:linked_target] + unlinked[:unlinked_target]
    remaining = total - len(chosen)
    # If one stratum has too few elements, fill from the other.
    chosen.extend(linked[linked_target:linked_target+remaining])
    remaining = total - len(chosen)
    chosen.extend(unlinked[unlinked_target:unlinked_target+remaining])
    for row in chosen:
        row["SamplingStratum"] = (
            "RETRIEVED_PAIR" if row["GlobalId"] in linked_ids else "NO_RETRIEVED_PAIR"
        )
    return chosen


def link_review_worksheet(sample_rows, ranked_links):
    """One frozen highest-ranked candidate per sampled element; truth blank."""
    first = {}
    for pair in ranked_links:
        first.setdefault(str(pair.get("GlobalId") or ""), pair)
    out = []
    for row in sample_rows:
        gid = str(row.get("GlobalId") or "")
        typ = str(row.get("IFCType") or row.get("SampleIFCType") or "")
        eligible = typ in SUPPORTED_CLASSES
        candidate = first.get(gid) if eligible else None
        out.append({
            "GlobalId":gid,
            "SampleIFCType":typ,
            "ElementName":row.get("ElementName", row.get("SampleName","")),
            "ObservedThickness_mm":row.get("ObservedThickness_mm",""),
            "SamplingStratum":row.get("SamplingStratum","MIXED_CLASS_COVERAGE"),
            "EvaluationEligible": "YES" if eligible else "NO",
            "PredictedTopCandidate": "1" if candidate else "0",
            "CandidateRequirementID": candidate["RequirementID"] if candidate else "",
            "CandidatePDFPage": candidate["PDFPage"] if candidate else "",
            "CandidateClauseText": candidate["ClauseText"] if candidate else "",
            "CandidateIFCMaterials": candidate["IFCMaterials"] if candidate else "",
            "CandidateReasons": candidate["Reasons"] if candidate else "",
            "CandidateStatus": (
                candidate["ScreeningStatus"] if candidate else
                "NO_CANDIDATE" if eligible else "CLASS_OUTSIDE_WALL_RETRIEVER"
            ),
            "verified_document_applies": "",
            # Reviewer enters PDF-P14-A1;PDF-P14-A2 (all genuinely applicable
            # requirements) or NONE if none apply. An empty cell is UNLABELLED.
            "ground_truth_applicable_requirement_ids": "",
            "ground_truth_property_comparable": "",
            "ground_truth_mismatch": "",
            "reviewer_notes": "",
        })
    return out


REVIEWER_EDITABLE = {
    "verified_document_applies", "ground_truth_applicable_requirement_ids",
    "ground_truth_property_comparable", "ground_truth_mismatch", "reviewer_notes",
}


def validate_frozen_review_rows(frozen, reviewed):
    """Reject edited predictions/measurements/clauses, duplicates, missing rows."""
    baseline=list(frozen)
    submitted=list(reviewed)
    if not baseline or len(baseline)!=len(submitted):
        raise ValueError("Reviewed sheet must contain all original sample rows.")
    fieldnames=set(baseline[0])
    if any(set(x)!=fieldnames for x in submitted):
        raise ValueError("Reviewed worksheet must preserve all original columns.")
    ids=[str(x.get("GlobalId") or "") for x in submitted]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicate GlobalIds in reviewed worksheet.")
    originals={str(x["GlobalId"]):x for x in baseline}
    if set(ids)!=set(originals):
        raise ValueError("Reviewer must not replace or omit original sampled IFC GlobalIds.")
    for row in submitted:
        original=originals[str(row["GlobalId"])]
        for key in fieldnames-REVIEWER_EDITABLE:
            if str(row.get(key) or "") != str(original.get(key) or ""):
                raise ValueError(f"Frozen evidence/prediction modified in column: {key}")
    return True


def _truth_ids(value):
    """Unambiguous positive requirement IDs or explicit NONE; blank = unknown."""
    v = str(value or "").strip()
    if not v:
        return None
    if v.upper() == "NONE":
        return set()
    ids = [x.strip() for x in re.split(r"[;,]",v) if x.strip()]
    if not ids or any(not re.fullmatch(r"PDF-P\d+-A\d+",x) for x in ids):
        return None
    return set(ids)


def _metrics(rows):
    """Candidate-link precision/recall, with possible FP and FN on one wrong pair.

    A wrong candidate when another true clause exists incurs BOTH a spurious
    predicted link (FP) and a missed correct link (FN). Consequently TP+FP+
    FN+TN can exceed N_evaluated; this is a link-event confusion tally, not
    a conventional mutually exclusive binary element confusion matrix.
    """
    tp=fp=tn=fn=wrong_both=0
    for row in rows:
        expected = row["_truth_ids"]
        predicted = str(row.get("CandidateRequirementID") or "").strip()
        if predicted and predicted in expected:
            tp += 1
        elif predicted:
            fp += 1
            if expected:
                fn += 1
                wrong_both += 1
        elif expected:
            fn += 1
        else:
            tn += 1
    def div(a,b):
        return a/b if b else None
    precision = div(tp,tp+fp)
    recall = div(tp,tp+fn)
    return {
        "N_evaluated": len(rows), "TP":tp,"FP":fp,"TN":tn,"FN":fn,
        "N_wrong_candidate_and_missed_true_link": wrong_both,
        "precision":precision,"recall":recall,
        "F1":div(2*tp,2*tp+fp+fn),
        "top1_exact_link_accuracy":div(tp+tn,len(rows)),
    }


def evaluate_link_review(rows):
    """Calculate human-confirmed link-event scores with explicit exclusions."""
    all_rows = list(rows)
    included=[]
    per_type=defaultdict(list)
    excluded_class=excluded_document=excluded_unlabelled=0
    for row in all_rows:
        typ = str(row.get("SampleIFCType") or "")
        if typ not in SUPPORTED_CLASSES or str(row.get("EvaluationEligible") or "") != "YES":
            excluded_class += 1
            continue
        if _binary(row.get("verified_document_applies")) != "1":
            excluded_document += 1
            continue
        truth = _truth_ids(row.get("ground_truth_applicable_requirement_ids"))
        if truth is None:
            excluded_unlabelled += 1
            continue
        entry = dict(row, _truth_ids=truth)
        included.append(entry)
        per_type[typ].append(entry)
    result=_metrics(included)
    result.update(
        N_total_sampled=len(all_rows),
        N_unsupported_IFC_class=excluded_class,
        N_document_not_verified=excluded_document,
        N_ground_truth_unlabelled=excluded_unlabelled,
        N_excluded=excluded_class+excluded_document+excluded_unlabelled,
        metric_scope="reviewer-confirmed top-1 element-to-requirement link events ONLY",
        sampling_caveat="evidence-stratified sample; neither population accuracy nor project compliance",
        by_IFC_type={t:_metrics(group) for t,group in sorted(per_type.items())},
    )
    return result
