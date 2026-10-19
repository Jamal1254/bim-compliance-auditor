"""Reproducible sampling and binary misclassification metrics for a reviewed CSV.

Human reviewers must confirm whether the specifications apply to the model.
Definitions: positive = a real mismatch; negative = verified no mismatch.
Unknown, unclear, or nonapplicable examples are excluded, not assumed passes.
"""
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

POS = {"1", "yes", "true", "mismatch", "noncompliant", "fail"}
NEG = {"0", "no", "false", "match", "compliant", "pass"}


def _binary(value):
    k = str(value).strip().lower()
    if k in POS:
        return 1
    if k in NEG:
        return 0
    return None


def evaluate_records(records):
    cm = Counter()
    excluded = 0
    for row in records:
        pred = _binary(row.get("predicted_mismatch", ""))
        truth = _binary(row.get("ground_truth_mismatch", ""))
        if pred is None or truth is None:
            excluded += 1
            continue
        cm["TP" if pred and truth else "FP" if pred and not truth else "FN" if truth else "TN"] += 1
    tp, fp, fn, tn = (cm[x] for x in ["TP", "FP", "FN", "TN"])
    safe_div = lambda a,b: a / b if b else None
    precision = safe_div(tp, tp+fp)
    recall = safe_div(tp, tp+fn)
    return {
        "N_evaluated": tp+fp+fn+tn, "N_excluded": excluded,
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "precision": precision, "recall": recall,
        "F1": safe_div(2*tp, 2*tp+fp+fn),
        "accuracy": safe_div(tp+tn,tp+fp+fn+tn),
    }


def seeded_type_sample(rows, quotas, seed=2026):
    """Within-type random selection; user-chosen quotas are purposive/stratified.

    Does not assert statistical significance or across-project representativeness.
    """
    pools = defaultdict(list)
    for row in rows:
        pools[row["Type"]].append(row)
    rng = random.Random(seed)
    samples = []
    for typ, n in quotas.items():
        if n > len(pools[typ]):
            raise ValueError(f"Insufficient '{typ}' entries: {len(pools[typ])} < {n}")
        samples += rng.sample(pools[typ], n)
    return samples


def evaluate_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return evaluate_records(csv.DictReader(f))


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser(description="Evaluate human-labeled element-level predictions")
    parser.add_argument("csv_path")
    a = parser.parse_args()
    print(json.dumps(evaluate_csv(a.csv_path), indent=2))
