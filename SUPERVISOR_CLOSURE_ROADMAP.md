# Supervisor closure roadmap — 28 October 2026

## Original supervisor model now has its corresponding DEMONSTRATION PDF
- User has supplied `Project11.ifc` and the PDF used in the professor demonstration, `Contractual document sample.pdf` (Dorchester Living, 2014).
- **PDF page 14** describes 352 mm cavity-wall construction (102 mm outer masonry + 150 mm cavity + 100 mm inner block) for conditional two-storey external masonry walls; another facing masonry 352 mm description appears on page 14 and page 15.
- Original IFC units use feet; 12 wall layer totals near this reference are **350 mm (six)** and **350.04375 mm (six)**. None of the traced material-layer values are 350.4 mm. Cross-check a different property/geometry if the old screenshot displayed 350.4.
- The sampled IFC layer associations are single-layer materials; no evidence currently establishes their equivalence to the three-part cavity wall assembly. The IFC project metadata is generic and does not independently establish a Dorchester Living/Heyford Park contract relationship.
- The standalone `CASE_STUDY_PROJECT11_352MM.md` records the full conditional analysis. The app's new no-cost **full-PDF cavity-wall assembly search** identifies 352 mm as a nominal assembly candidate, not a verified rule for any GlobalId. Do not turn the arithmetic differences into compliance FAIL.
- Next: live test the exact IFC+PDF with assembly-search UI; then find a genuinely matched project/specification or use a controlled synthetic experiment, and annotate ground truth.

## Project target
Design and evaluate an IFC + project-contract PDF linking prototype using Neo4j-supported Graph-RAG, with traceable candidate retrieval, human applicability verification, deterministic comparisons, and measured precision/recall/F1 against independently checked ground truth.

## Test 4: actual exported observations (28 Oct 2026, 10:14 UTC)
- Original model hash and PDF hash are identical to Test 3; this is **not** a different project's generalisation test.
- Wall IFC evidence: 220 IfcWallStandardCase records, each 100 mm overall thickness from the material layer set, marked internal; no contractual comparison was made.
- Unverified screening CSV: 70 group-to-PDF candidate rows: 52 other/unclear, 15 incompatible measurement, 2 review candidates, 1 scope unverified.
- PDF page 28: "The walls should have a minimum thickness of 90mm", accompanied by "See para 2C38" and a diagram reference. A 100 mm wall cannot be marked a geometry mismatch merely because it is not **exactly** 90 mm. The full source paragraph and contract applicability remain unverified.
- PDF page 81: "Area of fire resisting wall with materials more than 1mm thick" was incorrectly labelled REVIEW_CANDIDATE; it addresses material thickness, not an overall 1 mm wall requirement.
- The 30-row ground truth worksheet contains exactly one IFC class and one thickness (100 mm); all independently verified labels are blank. It cannot support by-element-type performance estimates.
- Gemini required two attempts in the run and produced candidate evidence. No live ground-truth accuracy is established.

**Direct code changes in this branch:** reject material-thickness false candidates, detect directional 'minimum/maximum' clauses and prevent incompatible exact comparisons, add a local-only optional 30-element mixed-class sample without extra model or graph requests.

## Evidence from the previous run
- 220 IfcWallStandardCase objects; all exported with 100 mm material-layer thickness.
- 40 graph objects uploaded/retrieved (our chosen free-tier-conscious cap, not Neo4j's documented universal limit).
- Gemini 2.5 Flash returned unverified clauses in two API attempts.
- 220 NOT_ASSESSABLE results in evidence-only mode: no verified compliance outcomes.
- Colour-coded HTML report was generated.
- Page 9 passage concerns 90 mm cavity-wall **leaves** and 50 mm **cavities**. These are not comparable to 100 mm **overall wall thickness** in the IFC. The current test does not prove contractual document applicability.

## Supervisor comments and evidence
| Supervisor requested | Addressed in code | Next acceptance evidence |
|---|---|---|
| Architecture and module I/O | Architecture guide and modular files | Walkthrough on one real matched project |
| Explain extraction and matching | IFC sources and page-referenced screening | Show correct element-to-clause linkage, not just same words |
| Severity/mismatch colour-coded export | CSV and HTML with review-priority colours | Demonstrate PASS, mismatch, missing, abstained cases |
| 350.4 mm versus 352 mm | IFC native units and comparison operators | Re-examine original IFC and original project clause |
| Configurable LLM | Gemini models and prompt versions | Independent provider adapter remains optional |
| Prompt changes and repeatability | Prompt hashing and A/B repeats | A twice, B twice on frozen pair, report results |
| 25–30 diverse random samples | 30 sampled walls in wall-only mode | Mixed-element human ground truth needed for final supervisor objective |
| TP/FP/TN/FN and type variation | Evaluation functions | Calculate from independent annotations; report all exclusions |

## P0 — Safety and semantic correctness (implemented, verify live)
1. Prevent building-height, partial leaf, cavity width and insulation-layer values from becoming overall-wall-thickness thresholds.
2. Flag IFC external/internal and unsupported load-bearing/cavity-wall scope.
3. Add local grouped IFC wall-to-PDF candidate screening (review candidate, incompatible metric, scope unknown, unclear). Explicitly NOT verified contractual linkage.
4. Reuse one genuinely verified applicable requirement for a selected group of walls without one LLM call per wall.
5. Acceptance: all tests green; PDF page 9 leaf requirement must NOT appear as an overall wall thickness choice.

## Immediate next acceptance test after these fixes
1. Redeploy **the same development branch** and run the same IFC/PDF pair.
2. Confirm page-81 '1 mm materials' no longer appears as a potential **total wall thickness** comparison.
3. Confirm page-28 'minimum 90 mm' preselects MINIMUM rather than exact equality.
4. Click **Generate 30-element mixed-class sample from this IFC (no API cost)** and download the output; inspect class distribution. All ground truth remains blank, as expected.
5. Download refreshed wall screening CSV, metadata JSON and the mixed-class worksheet.
6. Confirm the code stays in evidence-only mode unless a real contract-to-model relationship and element-specific rule scope have independently been established.

## P1 — Full-chain demonstration (NEXT)
1. Obtain an IFC and its corresponding project contractual specification, or use a clearly labelled controlled synthetic fixture.
2. Independently find one exact total wall-thickness contractual requirement and its original PDF page.
3. Validate project association and the precise IFC GlobalId(s) to which it applies.
4. Show observed IFC thickness and its source, applicable contract clause/page, rule operator, tolerance and reproducible result.
5. Export the tested case with CSV and colour-coded HTML. Demonstrate a matched, mismatched and abstained case.
Acceptance: at least one genuine evidence-backed link with reproducible source evidence, and no invented PASS/FAIL.

## P2 — Research validation
1. Collect a seeded 25–30 element **mixed-type** ground truth, where matched source projects allow; note sampling bias and class coverage.
2. Independently annotate applicability, requirement, measurement, GlobalId and expected outcome.
3. Compare the Graph-RAG candidate rankings against keyword-only retrieval on the SAME cases, noting that existing candidate screening is local lexical filtering and **is not itself proof of Graph-RAG matching**.
4. Produce TP, FP, TN, FN, precision, recall, F1 and separate abstention rate, by type and overall.
5. Run prompt A and B twice each and record hash, model, errors, page references and result differences.
Acceptance: metrics computed from reviewable labelled records rather than self-reported claims.

## P3 — Supervisor-ready presentation
Show the module diagram, extracted evidence, matched link(s), colour reports, measured validation, prompt A/B results, limitations and free-tier design.

## Current operator instructions
Deploy branch wall-first-supervisor-2026-10-28 with app.py on Streamlit. Upload existing IFC/PDF. Select Wall. In the new unverified wall-group screening, inspect page-9 cavity-wall leaf clause and download wall_pdf_screening_unverified.csv. Do not tick contract verification unless independently established. Also download the refreshed metadata JSON.

## Remaining blockers
- Matched IFC + true contractual specification not yet supplied.
- Original 350.4 versus 352 mm case needs original model/requirement.
- Live revised Streamlit test and fully labelled ground truth pending.
- Mixed-class sampling is available locally; independent mixed-class ground-truth annotations and prompt A/B empirical evaluation remain pending.
- The PDF's actual source and relevant full paragraph (including para 2C38) are still required before interpreting page-28 as an applicable contract requirement.