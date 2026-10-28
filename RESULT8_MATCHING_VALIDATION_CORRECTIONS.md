# Result 8 — matching and validation correction (28 October 2026)

## Scope locked
Continue the original supervisor's IFC/PDF Graph-RAG project, using `Project11.ifc` and the original demonstration PDF as an **illustrative pair**, not a confirmed shared construction contract. The 350.4/352 Revit width adjustment was a deliberate extractor test, not an unresolved construction defect. Do not keep reopening it.

## Evidence from the user-supplied Result 8 export
The actual `element_specific_ranked_links_UNVERIFIED.csv` has **80** candidate rows across **54** distinct IFC GlobalIds and three PDF requirements:

| PDF clause candidate | Previous exported rows |
| --- | ---: |
| PDF-P14-A1 | 54 |
| PDF-P14-A2 | 13 |
| PDF-P15-A3 | 13 |
| **Total** | **80** |

Thirteen unique IFC wall instances were approximately **350.00/350.04 mm** against the 352 mm source assembly. Another **41** were distant numeric candidates under the first PDF requirement (observed 50, 100, 120, 150, 250, 300, 330 mm), sometimes differing by **302 mm**. All were marked `ASSEMBLY_NOT_ESTABLISHED` and `NOT_ASSESSABLE`. Therefore **80 is NOT 80 correct matches**.

## Corrections committed to this GitHub branch
1. `semantic_links.py`: eliminate distant numerical candidates without independent material-assembly cues. Retain a distant value only when there is a separate brick/cavity/block material-name cue; still never infer physical assembly equality. **Fair round-robin selection across PDF clauses** avoids one early clause consuming the 80-row cap. This keeps the rule project-independent and is tested with synthetic analogues of the Result 8 values. Based solely on the previously exported rows, expected surviving *proximity-only* candidates are 13 unique IFC walls × three clauses = **39 suggested pairs**. **This is an offline expectation, not a claim of a new Streamlit run.**
2. `link_validation.py`: generate a reproducible **30-wall evidence-stratified review cohort** (include both retrieved and non-retrieved walls) separate from the previously generated **30-element mixed-class coverage sample**. The latter had only **two walls**, so it must NOT be used to claim wall-matching accuracy.
3. Independent reviewers must enter `ground_truth_applicable_requirement_ids` (real applicable IDs, or explicit `NONE`) and confirm that the PDF is relevant to the IFC project. The application cannot pre-fill truth from its predictions.
4. The upload validator rejects changed IFC evidence, source pages, candidate IDs, predictions, omitted rows and duplicated GlobalIds.
5. Confusion counts distinguish correct top-1 links, spurious predicted links and missed relevant requirements. **A wrong predicted clause where a different true clause exists creates both FP and FN** (link-event accounting; not a standard exclusive binary confusion matrix). Unsupported IFC types, unverified documents and blank labels are explicitly excluded. Report top-1 retrieval precision/recall/F1 only on independently reviewed cases, never as design-compliance accuracy.
6. Existing Gemini, optional Neo4j, source citations, material/thickness provenance, no-verdict protections and CSV/HTML exports are preserved. The graph cap of 40 remains a chosen API-budget safeguard, not an official Neo4j free-tier limit.

## Supervisor requirements: what is finished vs what is missing

| Requirement | Code/evidence | Research limitation |
| --- | --- | --- |
| IFC extraction, units and PDF evidence | Existing IFC/PDF modules, Test 8 output | PDF is not independently shown to be this IFC project's contract |
| GlobalId-to-clause candidates | Relevant source/page/class/context ranking; false candidates removed | Reviewer has not validated the proposed links |
| Graph-backed context | Model-hash Neo4j, relevant 40-element selection, Gemini input | Graph causal lift over lexical baseline not empirically measured |
| Mismatch taxonomy and coloured report | Deterministic engine and labelled synthetic demonstration | Synthetic labels cannot prove real building compliance |
| LLM modularity | Gemini default and optional OpenAI provider | Optional OpenAI integration untested live |
| 25–30 cases / TP, FP, TN, FN | Mixed-class and evidence-stratified wall sheets, independent annotation protection, labelled metrics code | Real human labels not provided; **no real F1** |
| A/B repeatability | Prompt variants, hashes, repeated outputs machinery | Four actual model calls not executed; **no empirical repeatability result** |
| Revit adjusted width | Explained as deliberate measurement test | No further discrepancy investigation necessary |

## Final boundary and delivery
Code implementation and unit regression checks should be performed in GitHub without sending the user through more Streamlit rounds. Actual independently verified contract relevance, real-world F1 and observed repeated LLM outputs must remain **unreported** until corresponding evidence exists. Do not infer academic success from counts of candidate rows or tests alone.

Current branch: `wall-first-supervisor-2026-10-28`. Do not merge into `main` solely from offline tests.