# BIM Model ↔ Specification Evidence Auditor — Revision v4

**Purpose:** A general-purpose IFC/PDF research prototype, **not** an automatic certification or a substitute for an engineer or contract reviewer.

## What is generic now

- Accepts any user-supplied valid IFC file using IfcOpenShell's `IfcElement` hierarchy (e.g. IFC2x3/IFC4); no project filename or GlobalId is programmed into application logic.
- Reads `IfcUnitAssignment` through IfcOpenShell's unit conversion to millimetres (including feet, inches and metric units). Records original units and evidence source.
- Supports filtering by any IFC entity-class name or by categories; `All model elements` is the default. Excludes IFC feature/opening elements from the physical-element sample.
- Retrieves material layer thickness, explicit wall-related IFC dimensions and native overall door/window sizes. Missing, conflicting and noncomparable values are **not** automatically declared compliant or noncompliant.
- Extracts page-labelled *candidate* text from any searchable PDF; ranks multiple IFC classes fairly. Offers a low-confidence page-text fallback when a searchable document has no English component words.
- Neo4j model records are keyed by SHA-256 plus GlobalId, isolating simultaneous projects instead of merging evidence from two files into one BIM entity.
- Gemini proposes candidate clauses using source evidence and graph neighbours, **never** final contract verdicts.
- Generates a new reproducible, type-stratified sample of up to 30 individual GlobalIds from the **currently uploaded model**; never uses pre-stored example IDs.
- User enters their *own* reference value, tolerance, evidence citation and exact element scope for a synthetic or confirmed contractual rule.
- Supports explicit **wall thickness**, **door/window overall width and height** comparisons. Other IFC types remain evidence-only until validated class-specific measurements and appropriate rules are developed.
- Produces full CSV, human-review CSV, metadata JSON, graph and AI diagnostics. Evaluates confusion-matrix statistics only for independently reviewed, applicable and fully-labelled elements.

## What v4 explicitly does NOT promise

1. It cannot automatically infer that any particular uploaded PDF legally applies to a given IFC.
2. It does not make a reliable engineering judgment for every property in every IFC class. Unrecognised or ambiguous dimensions are shown as missing/unassessable.
3. Scanned-image PDFs must be OCR-processed beforehand; PDF text extraction is not OCR.
4. Keyword/LLM clause suggestions still require human review, especially for multilingual PDFs, exceptions, tables and drawings.
5. The 30-element test and one controlled thickness probe are NOT a verified contractual accuracy study. Precision/recall/F1 depend on independent labels and coverage.
6. Local tests mock IFC2x3/IFC4 object APIs; **real model interoperability and live Neo4j/Gemini checks still need to run in Streamlit**. One real PDF's candidate retrieval was additionally checked locally.
7. The optional Neo4j display processes up to 300 elements per run and shows up to 150 neighbours for the prototype. This cap is disclosed in the UI, not hidden.

## Test in Streamlit (safe: main branch remains untouched)

1. Create a **new** Streamlit Cloud test app from the v4 branch below, `app.py`. Do not replace the working main deployment.
2. Use your existing private Streamlit Secrets: `GEMINI_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (rotate any exposed Neo4j credential). No secrets are committed to GitHub.
3. Upload **any** IFC and its PDF. Start with `All model elements`, `Evidence extraction only`, Neo4j OFF, Gemini OFF. Verify counts, IFC classes, measurement provenance, candidate pages and current-model sample.
4. If possible, repeat with a **second, independent IFC model** and an independently sourced specification PDF. This is necessary before claiming cross-file generalisation.
5. Optional graph ON: check graph upload count/returned rows and metadata. Optional Gemini ON: check clauses with page evidence; turn on B - conservative for prompt-comparison experiments.
6. Controlled test: choose a wall from the exported CSV, select `Controlled synthetic test`, `Wall thickness`, enter your synthetic mm threshold and the wall's exact GlobalId. Keep material terms empty for pure geometry checks.
7. Verified rule mode: independently confirm contract/model and relevant clause; enter that exact value, tolerance and scope. The result is only a **user-confirmed single-rule check**, not full project approval.
8. For validation, download `ground_truth_for_uploaded_ifc.csv`, independently review applicable contract clauses and mark `verified_document_applies` as `yes`, `ground_truth_mismatch` 0/1. If the app produced a rule prediction, the `predicted_mismatch` column will already have 0/1 for assessable instances; otherwise leave it empty. Upload the reviewed CSV to calculate conditional metrics.

## Technical checks already performed

- 20 isolated local unit tests passed; Python compile checks passed.
- Test fixtures represent **two simulated models** using different classes, units and IFC schema families (not a full live IfcOpenShell integration test).
- The original user's separate PDF was successfully parsed for candidate text across wall, beam, slab, door and window references.
- `main` is not altered. The legacy v3 30-ID example worksheet may still exist in the branch history, but **v4 does not read it or match against its GlobalIds**.

## Supervisor tracking

| Supervisor requirement | v4 status |
|---|---|
| Modular processing and source traceability | Implemented in code; architecture diagram included |
| Per-GlobalId analysis, discrepancy categories and export | Implemented, live v4 test pending |
| 350.04/352 mm intentional probe | Proven on v3 against the example IFC; generic v4 rules support any user-defined threshold |
| Gemini model/prompt alternatives | Implemented; comparative experiment pending |
| Neo4j material/storey evidence | Implemented with model-hash isolation; live v4 check pending |
| 25–30 verified ground-truth observations | Dynamic sample workflow provided; human truth labels not yet provided |
| TP/FP/TN/FN/precision/recall/F1 | Evaluator exists; no unverified scores reported |
| Cross-file robustness and dissertation conclusions | Second independent real IFC/PDF and final dissertation writing pending |
