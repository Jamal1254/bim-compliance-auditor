"""Per-upload reproducible stratified element sample; no hardcoded GlobalIds."""
from collections import defaultdict
import csv
import io
import random


def _category(typ):
    t = str(typ).casefold().removeprefix("ifc").removesuffix("standardcase")
    return t or "unknown"


def sample_from_current_model(observed_rows, n=30, seed=2026):
    """Stratified sample from THIS uploaded model. Quotas are not population-proportional."""
    pools = defaultdict(list)
    seen = set()
    for row in observed_rows:
        gid = row.get("GlobalId")
        if not gid or gid in seen:
            continue
        seen.add(gid)
        pools[_category(row.get("IFCType"))].append(row)
    rng = random.Random(seed)
    for kind in sorted(pools):
        values = pools[kind]
        values.sort(key=lambda x:x["GlobalId"])
        rng.shuffle(values)
    out = []
    while len(out) < n and any(pools.values()):
        for kind in sorted(pools):
            if len(out) >= n:
                break
            if pools[kind]:
                out.append(pools[kind].pop())
    return out


def evidence_review_worksheet(sample_rows):
    result = []
    for r in sample_rows:
        label = r["IssueCategory"]
        result.append({
            "GlobalId": r["GlobalId"], "SampleIFCType": r["IFCType"],
            "SampleName": r.get("ElementName", ""), "ExtractedInRun": "YES",
            "ObservedThickness_mm": r.get("ObservedThickness_mm", ""),
            "ThicknessSource": r.get("ThicknessSource", ""),
            "ObservedMaterials": r.get("ObservedMaterials", ""),
            "RuleStatus": label,
            "verified_document_applies": "", "verified_spec_clause": "",
            "actual_requirement": "", "ground_truth_mismatch": "",
            "predicted_mismatch": ("1" if label in {"GEOMETRY_MISMATCH", "MATERIAL_MISMATCH", "MISMATCH_BOTH"} else "0" if label == "PASS" else ""),
            "reviewer_notes": "",
        })
    return result


def validation_csv(rows):
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue()
