# Supervisor Revision v3 — research testing branch

Do not replace the working main branch. This is an evidence and controlled-test prototype, not a construction approval system.

## Test A — deliberate single-wall discrepancy
1. Upload Project11.ifc and Contractual document sample.pdf.
2. Component type: Wall. Mode: Controlled synthetic test.
3. Required thickness 352 mm; tolerance 0 mm.
4. Rule applies to: One exact GlobalId.
5. GlobalId: 1TNtWJ3wP23fxn_QcLsoEm.
6. Neo4j OFF, Gemini OFF. Run evidence audit.

**Expected from previously exported result 2 (not yet verified on live v3):** observed 350.04 mm, difference -1.96 mm, GEOMETRY_MISMATCH for selected wall, NOT_APPLICABLE for other 102. This is synthetic and not an actual contractual failure.

## Test B — 30-element validation evidence
1. Component type(s): All sample types.
2. Mode: Evidence extraction only; Neo4j OFF, Gemini OFF.
3. Run and download 30-element evidence & ground-truth worksheet.
4. Verify all 30 GlobalIds have evidence. Do not assign real compliance truth until a valid and applicable specification is independently identified.

The provided sample contains 12 wall elements and 18 non-wall elements. Non-wall extracted candidate dimensions require class-specific definitions before contractual numerical comparisons.

## Supervisor progress
- Architecture flow diagram: v2 diagram retained.
- Element-level statuses / CSV and colour-coded categories: implemented; v3 live test outstanding.
- Correct 352 mm controlled probe: reproduced offline; exact GlobalId targeting implemented.
- Mixed-class evidence collection: implemented; v3 live test outstanding.
- Gemini prompts and Neo4j retrieval: implemented, not yet experimentally validated.
- 30 human ground-truth labels: 0 completed.
- TP/FP/TN/FN, precision, recall, F1: not valid until independent labels.
- Known IFC sample: 103 wall-related entities, 76 known thicknesses; 24 IfcWall and 3 IfcCurtainWall thicknesses unresolved.
- Tests: 15 passed locally. Live Streamlit/IFC integration is unverified.
