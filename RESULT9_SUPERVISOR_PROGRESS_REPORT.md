# Result 9 — Supervisor Progress Report
Date: 28 October 2026. Status: evidence extraction and candidate retrieval operational; controlled experimental verification and independent real-project accuracy outstanding.

## Objective
Improve the original IFC–PDF + Neo4j + Gemini research prototype in accordance with supervisor comments: explain architecture and element-to-clause matching, report categorised discrepancies, test the Revit width changes, evaluate 25–30 diverse elements with independently reviewed truth, and compare prompt repeatability.

## Actual Result 9 findings
- The current IFC is **unchanged Project11**: model hash c60b39389ba3d24e55c504c195af1020a47ebc9e2f1f3ede4802661af6215f85, matching earlier runs. The user did NOT upload an edited Revit IFC in Result 9.
- IFC evidence: 103 wall-related elements: 76 IfcWallStandardCase, 24 IfcWall, 3 IfcCurtainWall. One of the 100 ordinary walls lacks a reliable thickness measurement. All 103 are NOT_ASSESSABLE because project-specific contractual applicability is unknown.
- Original PDF evidence: three 352 mm nominal wall-assembly references (pages 14, 14 and 15). Source text describes separate brick 102 mm, cavity 150 mm and block 100 mm layers with other location/house-type conditions.
- Result 8 had **80 candidate links covering 54 distinct wall GlobalIds**. Result 9 has **39 candidate links covering 13 GlobalIds**, 13 per PDF clause. The removal of 41 distant numerical candidates is a positive software correction, **not a measured precision increase**.
- Those 13 current IFC walls declare one material layer of about 350.0 or 350.04 mm, not three verified brick/cavity/block layers. All 39 remain labelled ASSEMBLY_NOT_ESTABLISHED and NOT_ASSESSABLE. No contractual pass/fail may be claimed.
- Result 9 screenshot displays 40 retrieved Neo4j records and a Gemini 2.5 Flash source-referenced candidate response. Those demonstrate workflow activity, not retrieval accuracy.
- A 30-wall validation cohort has 13 retrieved plus 17 non-retrieved wall observations. A separate 30-element mixed-class sample exists. Neither has independently verified ground-truth annotations. Real-world precision, recall and F1 cannot be reported.
- The prior 350.4 mm versus 352 mm example was the student's deliberate Revit extraction test, NOT an actual building defect.
- A previous app revision added Dorchester-specific 352 mm and England-specific 90/50 mm runtime panels. Those project/jurisdiction-specific panels have now been removed from the main app and replaced with a generic, user-configured material-layer comparison. This is important to keep the product reusable across different IFC/PDF pairs.

## Software improvements after Result 9
- Added controlled_layer_comparison.py: the user selects a source passage from the uploaded PDF and enters the layer labels and expected values after checking that passage. The same code accepts any number of layers and arbitrary positive thickness values; no Project11 name, Dorchester clause, jurisdiction, material, or fixed dimension is built into the comparison.
- The generic comparison checks declared IFC layer counts and per-layer values, flags missing evidence and conflicting overall-width evidence for review, records the source page/text, and always leaves actual contractual applicability and building compliance unverified.
- The main Streamlit workflow no longer invokes the Dorchester 352 mm test or England AD A 90/50 mm test as special-case runtime logic. Specific values such as 102/150/100 are only one possible user-entered experiment, not defaults or universal rules.
- Existing IFC/PDF extraction, 39 improved element-to-page candidates, graph context, Gemini module, coloured exports, prompt experiments and mixed-class samples remain intact.

## Exactly what the student should do in Revit
**Do not convert every wall into the same construction.** You may edit many wall instances, but preserve different real wall categories as controls. Unrelated concrete walls, partitions and curtain walls should not be assigned a brick/cavity/block build-up just to force a match. Duplicate Revit wall types first so the source model stays intact.

1. Save a COPY of the Project11 Revit project with EXPERIMENT in its name.
2. For a controlled test of the chosen PDF passage, duplicate appropriate masonry wall types and define actual material layers. If you choose the Dorchester example, the PDF excerpt suggests the following test values; these are **experiment inputs only, not rules embedded in the software**:
   - EXP-352-BASELINE: 102 mm brick + 150 mm cavity + 100 mm block = 352 mm.
   - EXP-342-CAVITY: 102 mm brick + 140 mm cavity + 100 mm block = 342 mm; only cavity differs by −10 mm.
   - EXP-342-BLOCK: 102 mm brick + 150 mm cavity + 90 mm block = 342 mm; only block differs by −10 mm.
3. Apply those types to **relevant masonry wall instances**, ideally ten walls per group (30 walls) if sufficient. Leave unrelated walls untouched. Record the three type names, intended dimensions and Revit element IDs. Keep the original IFC intact.
4. Export the copied project to a **NEW IFC**, preserving the material-layer associations, and send only that new IFC and the simple type/expected-dimensions table. There is no need to rerun Streamlit or re-upload existing source PDFs/screenshots.

## What the assistant will do next
1. Inspect the new IFC against original Project11 by IFC GlobalId, wall type, material-layer count and mm conversions.
2. Compare declared brick/cavity/block layer values with the three deliberately authored controls and compile observable true/false **controlled dimension-detection** outcomes.
3. Test whether the PDF source page, material assembly and actual IFC IDs are correctly linked; revise code only for demonstrated defects.
4. Finalise the supervisor report: architecture, extraction and matching algorithm, error taxonomy, sample selection, test results, repeatability conditions, limitations and links to source/test evidence.

## Supervisor requirement status
| Requirement | Status | Missing evidence |
| --- | --- | --- |
| IFC extraction and PDF citation | Implemented and observed | Changed Revit IFC to demonstrate multi-layer effects |
| IFC GlobalId-to-PDF candidates | 39 source-referenced candidates, unverified | Independently applicable source/element links |
| Neo4j/Gemini workflow | Integrated; Result 9 screenshot shows both | Quantified gain over baseline not measured |
| Misclassification taxonomy and report | Implemented in synthetic and evidence-only modes | Revised real IFC to show intentionally changed dimensions |
| Revit 350.4 / 352 sanity test | Explained as controlled test | Closed |
| 25–30 mixed element types | Mixed sample machinery exists | Independent annotations and valid class-specific rules |
| TP/FP/TN/FN, precision, recall, F1 | Calculation logic tested | Real project match and verified ground truth |
| Prompt A/B repeatability | Tooling implemented | Actual repeated model responses |
| Final supervisor report | Progress documented here | Experimental IFC results and honest final interpretation |

## Research boundary
This test uses an illustrative IFC/PDF pairing. Project-specific contract provenance, wall scope, storey position, drawings and tolerances remain unconfirmed. Exact numeric equality to a sample assembly is not real-world compliance. A thirty-wall controlled trial does NOT replace the supervisor's separate diverse-element validation task. Do not invent verified contract accuracy or repeatability metrics.
