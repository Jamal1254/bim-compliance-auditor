# Original professor demonstration: Project11.ifc vs Contractual document sample.pdf

**Evidence audit date:** 28 October 2026. **Status:** numeric sources traced; contractual/model applicability NOT established.

## Document evidence

The uploaded 2014 *Dorchester Living Construction Specification*, cover identifying Heyford Park House, Heyford Park, Camp Road, Bicester, contains on **PDF page 14**:

- Under *External Masonry Walls → Walls below Damp Proof Course → 2 Storey Houses*: **352 mm cavity wall construction** with outer 102 mm brickwork, 150 mm cavity and inner 100 mm blockwork (102 + 150 + 100 = 352 mm).
- Under *Walls above Damp Proof Course*: **352 mm facing masonry** with the same primary brick/cavity/block thicknesses (other finish layers are mentioned separately).
- PDF page 15 gives a related 352 mm facing masonry description under *3 Storey Houses*.

This is an **assembly-level nominal design description**, NOT an automatic lower bound for every wall, and NOT a single-leaf thickness.

## What is actually present in the model

`Project11.ifc` is IFC2X3 exported via Autodesk Revit 2024 with authoring metadata dated September 2026. Its project fields are generic (`Project Number` / `Project Name`), not an independently established Dorchester Living/Heyford Park link. IFC native length is **FOOT** (1 foot = 304.8 mm).

Within the latest Test 6 extraction of 103 wall-related IFC objects (76 IfcWallStandardCase, 24 IfcWall, and 3 IfcCurtainWall):
- Six wall instances of `Mauerwerk - Stein Bestand 350` use **1.148293963254593 feet**, which converts to **350.00000 mm**.
- Seven other wall instances (including `Ortbeton - STB 200` and `Mauerwerk - Stein Bestand 800`) use **1.1484375 feet**, which converts to **350.04375 mm**.
- Their model material-layer associations reference a **single layer**, not an independently verified 102+150+100 mm cavity assembly.

That makes **13** wall instances numerically near 350 mm (six at 350 mm, seven at 350.04375 mm). These are observed IFC evidence values, not design defects.

## Explaining the professor's 350.4 versus 352 example

- The sample PDF **does contain 352 mm**, but only within conditional wall assembly specifications. Three whole-assembly references are detectable: PDF pages **14, 14, 15**.
- Direct numeric differences from the above IFC material-layer totals are:
  - 350.00000 - 352 = **-2.00000 mm**;
  - 350.04375 - 352 = **-1.95625 mm**.
- The **350.4 mm** number from the prior demonstration does **not** agree with these 13 declared material-layer totals. It might come from a different element/property/geometry result, but has **not** been traced. Do not present 350.4 as independently confirmed.
- No automatic geometry mismatch can be concluded without confirming a specific wall GlobalId, the actual comparable assembly property, contract-project association, precise wall category/storey/position, and any permitted design tolerance.

## Application correction

The previous parser rejected all excerpts containing `cavity`, which was sensible for cavity-leaf thickness but prevented it from surfacing bona fide *overall cavity-wall construction* descriptions like the 352 mm clause. New code now performs a separate **full-PDF nominal cavity-wall assembly search**. It displays source page, extracted phrase and source context, but leaves `IFCElementLink` and `ContractualApplicability` set to `NOT_VERIFIED`, rather than claiming pass/fail. Existing total-thickness comparison remains protected from 90-mm leaf/50-mm cavity confusions.

## Supervisor-facing demonstration sequence

1. Upload **Project11.ifc** and **Contractual document sample.pdf**; select `Wall`.
2. Run **Evidence extraction only**. Optionally enable Neo4j and Gemini but no additional API calls are necessary for the next step.
3. Click **Find wall-assembly specifications throughout full PDF (no API cost)**. Confirm 352 mm and inspect PDF page 14–15.
4. Pick the actual wall GlobalId from the IFC evidence export and inspect its layer composition and units.
5. Show the numerical difference **as a candidate analysis**, and explicitly explain why a contractual verdict is not justified without a real project/assembly match.
6. For demonstration of classification algorithms, use **Controlled synthetic test** with a user-labelled hypothetical rule, not Verified contractual rule.
7. The final 25–30 element accuracy assessment requires independently verified contract applicability and human-labelled ground truth; placeholders are not acceptable.

This case study supports the supervisor's demand for traceable extraction and limitations, but it is **not** a verified real-project compliance test.
