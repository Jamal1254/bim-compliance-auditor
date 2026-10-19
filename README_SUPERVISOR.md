# BIM Compliance Auditor — Supervisor Revision v1 (local prototype)

**Status:** Revised source, syntax-checked; five unit tests passed. **Not** end-to-end tested using live Neo4j/Streamlit/Gemini. The supervisor revision is maintained on a separate testing branch; the deployed application and main branch are unchanged.

## Supervisor comment coverage

| Comment | Current action | Status |
|---|---|---|
| Modular flow + inputs/outputs | `architecture.svg`, `.png`, editable `.dot` | Diagram drafted |
| Explain extraction/matching | IFC dimension provenance (`WidthSource`), deterministic element-level matching in `audit_engine.py` | Implemented for explicit rule testing |
| Colour-coded severity + export | Streamlit per-element matrix and CSV export | Code drafted, runtime not tested |
| 350.4 vs 352 mm | Controlled mismatch test; 1.6 mm deviation, exact-match tolerance 0 | Unit test passed |
| Neo4j and graph evidence | Retrieve element, containment and material neighbours and pass evidence to the LLM; no global database delete | Drafted; live graph retrieval untested |
| 25–30 element sampling | `sample_30_elements.csv`, selected by seeded type-stratified sampling | Sample generated; **not** labelled ground truth |
| Confusion matrix metrics | `validation.py`, `ground_truth_blank_template.csv` | Calculator tested; real labels not yet supplied |
| LLM models, prompts, repeatability | Planned controlled experimental phase | **Not yet completed** |

## Important evidence caveat

`Project11.ifc` describes a Revit-authored building with German construction terminology and imperial (FOOT) project length units. The provided *Dorchester Living Construction Specification (2014)* is a UK specification. Their actual contractual relationship is **not established**. For your deliberate 352 mm test, choose the synthetic all-elements scope **only to probe mismatch detection**. Do not report project compliance, research accuracy, or a confusion matrix from this mismatch without independently verified ground truth.

The 352 mm reference appears in the contract, PDF page 14, under External Masonry Walls, but applies to particular wall assemblies and positions; it is not a universal wall-thickness rule.

## Deployment steps (on a separate branch)

1. **Rotate the exposed Neo4j password immediately.** The previous credential was present in the committed file and may remain recoverable in Git history. Changing the file alone is insufficient.
2. This code is available on the supervisor testing branch. Review and deploy that branch separately after configuring secrets.
3. Configure Streamlit secrets: `GEMINI_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Do not commit `.streamlit/secrets.toml`.
4. Start with `streamlit run app.py` using the uploaded IFC/PDF. Enable the human-confirmed rule only for controlled tests; inspect individual GlobalIds.
5. Check results from full extracted-elements CSV against the enhanced verified-rule CSV; check Neo4j graph evidence retrieval in the sidebar.
6. Repeat experiments with known appropriate specifications, a known-ground-truth review sheet, multiple categories, and controlled prompts; make no unverified performance claims.

## Validation template

Use `sample_30_elements.csv` to locate selected model elements. Add independently verified contract evidence before entering `ground_truth_mismatch` (0=no mismatch, 1=has mismatch). Record actual system output in `predicted_mismatch` separately. Empty means not yet assessed. The two data sources should be checked independently, then evaluated with:

```
python validation.py ground_truth_blank_template.csv
```

The first evaluation will have N=0 until labels are collected. **Never treat missing labels as negatives.**

## Technical decisions and limitations

- **IfcOpenShell** is used for IFC instance metadata, material layers, and geometry; it retains `GlobalId` for traceability.
- **pypdf** gets specification text with page references. A PDF/IFC pair does not prove contractual applicability.
- **Neo4j** stores element, storey, and material graph links; graph records can now be retrieved for the LLM narrative. Full semantic Graph-RAG clause-to-element mapping remains a future improvement.
- **Human-confirmed rules** permit deterministic, reproducible per-element checks without depending on LLM wording.
- **LLM** remains useful for narrative summaries but must not be used as the source of validation ground truth.
- IFC units are in **feet**. Material-layer IFC-native lengths are converted to mm; IfcOpenShell geometry coordinates are assumed to be in metres and converted with 1000 mm/m (unless `CONVERT_BACK_UNITS` is enabled). The latter is a hypothesis to confirm with your deployed IfcOpenShell version.
- `WidthSource` tracks where each dimension came from. An axis-aligned bounding-box width is only a rough fallback for non-rectangular/rotated elements.
- Code has not been tested end-to-end here because `ifcopenshell`, `streamlit`, `google-genai`, `neo4j` cannot be installed in this restricted runtime.
