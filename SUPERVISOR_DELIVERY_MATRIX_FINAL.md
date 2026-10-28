# Supervisor corrections — delivery and acceptance matrix (28 October 2026)

## Fixed project and research goal

This is the original **IFC + PDF technical specification Graph-RAG research prototype**. Do not rebuild it, swap models without reason, or turn it into a generic standalone wall-dimension checker. The goal is to extract IFC and PDF evidence, propose element-specific requirement links with Neo4j-backed context and LLM assistance, preserve uncertainty, generate auditable classifications, and evaluate independent ground truth.

**Primary case:** `Project11.ifc` and `Contractual document sample.pdf` — the pairing used for the professor demonstration, NOT independently shown to be the same construction project. **Secondary interoperability case:** `02 Multifamiliar Formato Linear - Arquitetônico.ifc` and `Walls_for_IFC_Software.pdf` — also not independently confirmed as one project. Both must be labelled illustrative when testing contractual applicability.

## Reusability guardrail — do not hard-code the sample project

The production Streamlit workflow must not assume Project11, Dorchester, England, 352 mm, or a fixed brick/cavity/block layer sequence. `controlled_layer_comparison.py` accepts user-confirmed layer labels and thicknesses for whichever PDF passage is selected. The source-specific 352 mm and England 90/50 mm runtime panels were removed. Such numbers may appear in a **test case or case-study report**, but they are not defaults or universal rules. PDF candidates remain unverified until scope and model applicability are checked.

## Exact supervisor comment -> implemented feature -> evidence

| Supervisor's comment, 13 Oct 2026 | What is now implemented | Remaining acceptance |
| --- | --- | --- |
| Visual flow of modules; clarify input/output and modular/tactical choices | `WALL_FIRST_SUPERVISOR_GUIDE.md`; modular extraction, PDF parsing, ranking, graph context, LLM gateway, deterministic audit, CSV/HTML, sampling | Demonstrate the same workflow live and annotate architectural trade-offs |
| Explain exactly how extraction and matching work | `check_ifc_compliance.py` preserves declared IFC units/GlobalIds and rejects guesses; `spec_context.py` extracts source-page requirements; `semantic_links.py` ranks source-to-GlobalId candidates and explains uncertainty; `ifc_to_neo4j.py` stores model-isolated material/storey relations and returns the most relevant 40 records first | Independent element-level applicability labels are required to measure true linking accuracy |
| Export colour-coded severity/mismatch categories | `audit_engine.py`, `reporting.py`, `controlled_demo.py`; categories include missing geometry/material/both, geometry/material/both mismatch, pass and review; export CSV and printable HTML | The full legend can be shown in the **clearly labelled synthetic demonstration**. Actual contractual classifications require real applicability |
| 350.4 mm vs 352 mm | Original IFC uses feet -> mm; 13 sample IFC wall layers are 350.0000 or 350.04375 mm; PDF pages 14–15 show 352 mm nominal cavity-wall assembly (102+150+100). Numerical differences are -2.0000 or -1.95625 mm. See `CASE_STUDY_PROJECT11_352MM.md`. | User confirmed the Revit wall width was deliberately edited before IFC export as a controlled extractor test; **do not treat the 350.4/352 comparison as a physical construction defect**. PDF–model contractual provenance and comparable wall assembly still remain unverified; no automatic FAIL claim. |
| LLM modularity / replacing API | `llm_gateway.py` supports Gemini (default) and optional OpenAI Responses API, without changes to IFC/graph/rules; provider and actual model are recorded. No new key needed for existing Gemini workflow | OpenAI live request remains untested and optional; do not spend money unless comparison is academically required |
| Prompt influence on outcome | A and B controlled prompts, version hashes, model metadata and source context | Press A/B button once (4 total requests, user permission and free-tier cap permitting), export JSON; cannot manufacture repeated-model outputs |
| Repeatability | Response hashes, PDF page citations, model used, provider errors and repeated-output comparison | Actual A twice/B twice empirical data required |
| 25–30 diverse random objects | `validation_export.py` now automatically generates mixed-class stratified 30-element sample from uploaded IFC; no API calls | Sampling is stratified/purposive and not proof of statistical significance |
| Actual ground truth from technical specifications | `link_validation.py` attaches top-1 page/requirement candidates per GlobalId; leaves human applicability and mismatch labels blank | An independent reviewer must confirm the contract-to-model relationship and annotate true/false links/measurements |
| TP/FP/TN/FN and variations by element type | `validation.py` and `link_validation.py` compute confusion matrix, precision, recall, F1, exclusions, and per-type counts from independently labelled CSV | No real accuracy result possible while uploaded truth columns are blank. Top-1 retrieval is not full-document recall or design compliance F1 |

## Latest Test 7: already supplied; DO NOT ask user to rerun it for diagnosis

- 103 wall-related IFC objects, one unresolved wall thickness among 100 wall-class objects, and three curtain walls.
- Model-graph upload 40, graph retrieval 40; one Gemini 2.5 Flash attempt completed without reported error.
- Three PDF nominal 352-mm assembly references on pages 14, 14 and 15.
- Thirteen IFC wall observations numerically close to 352 mm (350 or 350.04375).
- Current model-to-PDF matching cannot establish contractual applicability or equivalent assembly structure. All 103 remain NOT_ASSESSABLE, correctly.
- Test 7 Gemini gave class-level clauses, not reviewed GlobalId applicability. `semantic_links.py` and ranking-aware graph+LLM context address the software part of this gap.
- 30-element ground-truth worksheet is **blank**, thus no real F1; no prompt A/B repeat yet.
- Result 9 used the original IFC, not the user's new Revit export. The new export is needed only for the controlled layer-extraction experiment, not to make the application project-specific.

## Complete code implementation status

- **Implemented and unit tested:** IFC extraction, PDF source detection, candidate-to-GlobalId ranking, bounded Neo4j context selection, Gemini/OpenAI provider adapters, A/B repeatability machinery, separation of evidence and validated rules, deterministic classified comparisons, colour-coded report, mixed-class sampling, independently reviewed top-1 candidate metrics, and the project-independent user-configured material-layer comparison.
- **Not yet independently observed in a deployed app since the latest commits:** live Streamlit UI on actual Project11/spec, integrated Graph-RAG + provider output. CI proves pure logic and syntax only.
- **Not yet a defensible real-world study:** independent document/model match, expert annotation of 25–30 sampled cases, actual A/B repeated responses and statistical comparison. Do not fabricate these results.

## Final acceptance conditions — do not request more tests from the user

1. Deploy branch `wall-first-supervisor-2026-10-28`, `app.py`. Project11 + the uploaded Dorchester PDF can remain one **illustrative test pairing**, but the app does not assume they are the same project. Select a PDF passage in the generic layer-comparison panel and manually confirm the ordered layer values for the controlled experiment. Candidate discovery/ranking is reusable for other IFC/PDF uploads.
2. Turn on Neo4j and Gemini only if free-tier budget permits. Show source PDF page, candidate GlobalId, IFC measured layer and material/storey graph neighbours, LLM suggestion, uncertainty and export. This is candidate retrieval, not contractual PASS/FAIL.
3. Open the **synthetic-only categories** expander for clearly labelled eight audit outcomes. Download the report.
4. Download **automatically generated 30 mixed-class sample** and **top-1 clause review worksheet**. Reviewer should annotate actual project/contract applicability and relevance. If same-project contract cannot be verified, label case as *illustrative* and metrics as unavailable, not high accuracy.
5. Optional single A/B repeat run (four provider calls) on frozen inputs and record actual outputs.
6. Present limits: PDF-to-IFC project provenance unknown, nominal layer-vs-assembly comparability, graph 40-record budget, and missing independent ground truth.

## Merge gate

Do NOT merge the development branch to `main` until actual Streamlit integration is checked, export opens correctly, and the limitations are faithfully reported. The original `main` and `original-code-supervisor-fix-2026-10-20` remain intact.
