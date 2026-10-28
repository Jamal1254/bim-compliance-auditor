# Supervisor closure roadmap — 28 October 2026

## Project target
Design and evaluate an IFC + project-contract PDF linking prototype using Neo4j-supported Graph-RAG, with traceable candidate retrieval, human applicability verification, deterministic comparisons, and measured precision/recall/F1 against independently checked ground truth.

## Evidence from the latest run
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
3. Compare the Graph-RAG candidate rankings against keyword-only retrieval on the SAME cases.
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
- Mixed-class validation and prompt A/B empirical evaluation pending.