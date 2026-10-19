"""Prepare an evidence-only worksheet for a manually verified 30-element sample."""
import csv
import io

def merge_validation_sample(sample_csv, observed_rows):
    if isinstance(sample_csv, bytes):
        sample_csv = sample_csv.decode("utf-8-sig")
    sample = list(csv.DictReader(io.StringIO(sample_csv)))
    ids = [row.get("GlobalId", "").strip() for row in sample]
    if len(set(ids)) != len(ids) or any(not x for x in ids):
        raise ValueError("Validation sample requires unique, nonempty GlobalIds")
    index = {row.get("GlobalId"): row for row in observed_rows}
    output = []
    for sample_row in sample:
        obs = index.get(sample_row["GlobalId"])
        output.append({
            "GlobalId": sample_row["GlobalId"],
            "SampleIFCType": sample_row.get("Type", ""),
            "SampleName": sample_row.get("Model_Name", ""),
            "ExtractedInRun": "YES" if obs else "NO",
            "ExtractedIFCType": obs.get("IFCType", "") if obs else "",
            "ObservedThickness_mm": obs.get("ObservedThickness_mm", "") if obs else "",
            "ThicknessSource": obs.get("ThicknessSource", "") if obs else "",
            "ObservedMaterials": obs.get("ObservedMaterials", "") if obs else "",
            "RuleStatus": obs.get("IssueCategory", "NOT_EXTRACTED") if obs else "NOT_EXTRACTED",
            "verified_document_applies": "",
            "verified_spec_clause": "",
            "actual_requirement": "",
            "ground_truth_mismatch": "",
            "predicted_mismatch": "",
            "reviewer_notes": "",
        })
    return output

def validation_csv(rows):
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
