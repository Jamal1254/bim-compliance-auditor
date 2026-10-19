# BIM Auditor — Supervisor Revision v2 (testing branch)

**Scope:** research prototype; it is not an engineering sign-off tool. This branch must be deployed as a *separate* Streamlit app. Do not replace `main` before testing.

## Run in Streamlit Community Cloud

- Repository: `Jamal1254/bim-compliance-auditor`
- Branch: `supervisor-revision-v1-2026-10-19` (branch name preserved to avoid disrupting the existing deployment)
- Main file: `app.py`
- Add Secrets for `GEMINI_API_KEY` only if you plan to enable optional AI clause suggestions. Neo4j credentials are required only if you enable graph retrieval.
- **Never commit secrets.** Rotate the previously exposed Neo4j password and clean leaked Git history separately.

## Recommended first run

1. Upload the same IFC (`Project11.ifc`) and the Dorchester PDF.
2. Set **Evidence extraction only**, leave **Neo4j** and **Gemini** off, and run.
3. Confirm the complete element CSV and all rows `NOT_ASSESSABLE` (even when thickness is known).
4. Set **Controlled synthetic test**, thickness **352 mm**, tolerance **0 mm**, scope **ALL extracted elements (synthetic only)**. It is expected to report mismatches. These are **not contractual failures**.
5. Test the intended 350.4 mm injected value against raw IFC extracted thickness. A reported 350.04 mm is **different** from 350.4 mm; note the exact observed value and check how it was exported.
6. Use verified contractual-rule mode only after independently establishing this contract applies to the IFC project and confirming the exact clause applies to the chosen set of elements.
7. Optionally enable graph retrieval and then Gemini candidate clause discovery. They must not change the deterministic CSV results.

## Corrections against supervisor feedback

| Supervisor request | Delivered / remaining |
|---|---|
| Module diagram / inputs and outputs | Updated `docs/architecture_v2.svg` and editable `.dot` |
| Exact extraction and matching | Type-only IFC class matching; `WidthSource`; deterministic per-GlobalId audit; PDF page-reference candidates |
| Severity categories and export | PASS, geometry/material mismatch, missing dimensions/materials, scope unknown, NOT ASSESSABLE; CSV filters and full download. Severity is **review priority**, not structural safety rating. |
| Why 350.4 mm rather than 352 mm | Logged as deliberate artificial mismatch probe; must check whether observed model actually stores **350.04 mm**. |
| API/prompt/repeatability | Optional Gemini 2.5/2.0 model selector; two fixed prompt variants and SHA-256 of prompt; comparative trials still needed |
| 25–30 element validation | Prior `sample_30_elements.csv` is an unlabeled **sampling frame**, not validation; ground-truth labeling and metric analysis remain |

## Fundamental distinction

- **IFC observation:** a geometric/material value or an unresolved field.
- **Candidate specification clause:** a PDF passage with a page reference; project applicability not established.
- **Controlled synthetic test:** rule deliberately applied to test software detection, not project compliance.
- **Verified rule test:** only run when the human reviewer confirms *both* document-model project relevance and element applicability.
- **Report:** all numeric classifications from `audit_engine.py`, **never from free-form Gemini text**. Gemini can only suggest candidate clauses for a reviewer.

A completed dissertation validation requires independent labelled ground truth. The 2014 UK Dorchester construction specification and the supplied German-named IFC model have **no established common project origin**; do not present all resulting mismatches as real contractual failures.

## Local checks performed

`python -m pytest -q tests/test_supervisor_fixes.py` (unit tests run without Neo4j/Gemini/Streamlit) and Python syntax compilation. The contract PDF was independently parsed with `pypdf` to verify the 352 mm clause is retrieved with its page marker. **No full IFC/OpenShell runtime execution is claimed here**: `ifcopenshell` is not installed in the authoring environment. Run an end-to-end Streamlit test before relying on code.
