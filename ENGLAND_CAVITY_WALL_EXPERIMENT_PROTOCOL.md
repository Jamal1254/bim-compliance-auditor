# England guidance + Revit/IFC controlled experiment

## Why this protocol exists

This is **a controlled experiment (Option A)** using an existing model as a hypothetical design assessed against selected England guidance. It is not a verified UK construction project or contractual-compliance report (Option B).

**Observed IFC provenance:** The supplied `02 Multifamiliar Formato Linear - Arquitetônico(1).ifc` is IFC2X3, exported from Autodesk Revit 2024 on 2026-10-25. The internal project description is `CURSO DE REVIT ARCHITECTURE`; building name `Residência Multifamiliar Linear`; building storeys are `Pavimento 01`, `PAVIMENTO 02`, and `PAVIMENTO 03`. Embedded project address/coordinates point to João Pessoa, Brazil (approximately -7.099, -34.835), not an English construction site. **Do not present it as a real UK building or alter metadata to disguise provenance.**

**Observed model walls:** 220 `IfcWallStandardCase` elements, with one `IfcMaterialLayerSet` called `Basic Wall:10CM` containing a single `0.100 m` `.Alvenaria_Tijolo` layer. There is no three-layer cavity structure in this original IFC. That is **missing evidence of cavity construction**, not an automatically noncompliant physical cavity wall.

**Reference PDF:** `Walls_for_IFC_Software(1).pdf`, a compilation of Approved Documents for England. It contains Approved Document A, Section 2C, paragraph 2C8 on **PDF page 9** (printed Approved Document page 14). This guidance, *subject to all relevant Section 2C applicability conditions*, describes masonry cavity wall leaves of at least **90 mm** each and a cavity of at least **50 mm**. The same section includes other conditions including building size, wall types, wall ties, structural context and storey restrictions. These three dimensions alone cannot certify the design. Approved Documents are guidance, not automatically contract clauses.

For current source, consult the England government publication: https://www.gov.uk/government/publications/structure-approved-document-a. Part B has separate editions and September 2026 amendments; do not casually apply mixed-era fire-safety excerpts as universal requirements.

## User tasks — only when ready for the controlled study

1. **Save a copy** of the original Revit project, with `EXPERIMENT` in its filename. Keep the original file unchanged.
2. Create **three clearly named test wall types** in that copy. They should be ordinary masonry cavity walls with exactly **three actual IFC-exported layers** in this sequence: `Brick outer leaf`, `Air gap cavity`, `Block inner leaf`. Assign *distinct material names* to the layers, not just a total type width.
3. Use these **deliberately chosen values** (millimetres):

| Named control | Brick layer | Cavity layer | Block layer | Revit total | Expected numerical-only finding |
|---|---:|---:|---:|---:|---|
| EXP-CAVITY-A-BASELINE | 100 | 50 | 100 | 250 | Within selected two leaf/cavity thresholds |
| EXP-CAVITY-B-THIN-LEAF | 80 | 50 | 100 | 230 | First masonry leaf under 90 mm |
| EXP-CAVITY-C-NARROW-GAP | 100 | 40 | 100 | 240 | Cavity under 50 mm |

4. Place one clearly identifiable wall instance of each type (or duplicate an existing wall in the **copy** and assign the experimental types).
5. Export the **copy** to `.ifc` with material-layer sets preserved. Verify all three layers and their names appear in the new IFC. Do **not** overwrite the original IFC or claim this is real UK contract data.
6. Save the original and altered IFCs together with an independent table of the *intended* changes (case name, Revit target dimension, export date). These are controlled design labels, not independently verified contractual annotations.

## Code behaviour (committed)

- `check_ifc_compliance.py`: reads actual ordered IFC `IfcMaterialLayerSet` entries into `MaterialLayers`, with layer name, thickness in mm, layer index and evidence source.
- `spec_context.py`: searches the **uploaded PDF itself** for source page and text of England AD A §2C8, including 90/50 mm.
- `controlled_cavity_test.py`: checks only numeric evidence on a three-layer masonry/cavity/masonry assembly. It marks a single-layer wall `EVIDENCE_INSUFFICIENT`; a mismatch in summed values `REVIEW_REQUIRED`; and a deliberately thin leaf/cavity as `DIMENSIONAL_DEVIATION_IN_CONTROLLED_TEST`.
- `app.py`: shows a separate **controlled cavity-wall layer experiment** table and downloadable CSV with PDF provenance. It does not send each wall separately to Gemini/Neo4j.
- All experimental outcomes retain `ContractualApplicability=NOT_VERIFIED` and `FullBuildingCompliance=NOT_ASSESSABLE`. Never replace these with genuine UK PASS/FAIL certification.
- Existing Graph-RAG, 30-wall and 30 mixed-class sampling, source citations and API budgets remain intact.

## Scientific targets and honesty

1. **Extraction correctness:** Do the three exported leaf/cavity values match Revit's intentionally recorded inputs? Expected class-specific numeric detection is testable.
2. **Sensitivity:** Does deliberately changing 100 → 80 mm outer leaf, or 50 → 40 mm cavity, change the corresponding numerical-only result while leaving other checks unchanged?
3. **Explainability:** Can a reviewer trace each finding to `GlobalId`, `MaterialLayers`, IFC unit conversion and PDF page 9 / §2C8?
4. **Optional full Graph-RAG tests:** Are the correct clause and relevant wall selected for each of the new examples? Report model outputs and errors only if actual API runs occur.
5. **Accuracy reporting:** Three designed cases show software behaviour, NOT statistical precision/recall/F1 on real project contracts. Those require independently verified source/model applicability and labels.

## When is Option B genuinely possible?

A UK-based regulatory/contractual assessment needs an IFC model whose project location and use are independently confirmed in England, its relevant edition/jurisdiction/design and approval dates, and authentic project requirements. Merely using an England PDF with a Revit model originally authored elsewhere does not supply this evidence.

**No further tests of the old original model are required.** The controlled Revit modification is a new, deliberate experiment, not another repeated debugging run.
