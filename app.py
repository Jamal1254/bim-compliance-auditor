"""BIM Evidence Auditor v4 — general IFC/PDF, cautious verified comparisons.

This is research software. It NEVER certifies a construction or contract.
Every rule requires a person to set applicable class, scope and citation.
"""
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from audit_engine import AuditRule, MEASUREMENT_TYPES, audit_elements, categories_summary, issue_colour
from check_ifc_compliance import extract_all_ifc_wall_dimensions
from spec_context import clause_candidates, candidates_text, adjacent_pdf_context, find_wall_assembly_specifications
from llm_assistance import PROMPT_VARIANTS, prompt_for, prompt_sha256
from llm_gateway import run_evidence_model, PROVIDER_MODELS, SECRETS
from validation_export import sample_from_current_model, evidence_review_worksheet, validation_csv
from validation import evaluate_records
from link_validation import link_review_worksheet, evaluate_link_review
from controlled_demo import synthetic_classification_examples
from evidence_linking import link_pdf_evidence
from wall_focus import wall_numeric_candidates, wall_thickness_references_mm, comparable_wall_group, review_wall_batch, screen_wall_clause_groups, comparison_hint
from reporting import colour_report_html
from assembly_evidence import numerical_wall_assembly_neighbours
from semantic_links import rank_element_requirement_candidates, select_graph_elements, format_grounded_link_context
from prompt_repeatability import record_output, summarise_repeats
from pypdf import PdfReader

APP_VERSION = "Wall-first supervisor iteration 2026-10-28"
st.set_page_config(page_title="BIM Evidence Auditor v4", page_icon="🏗️", layout="wide")
st.title("🏗️ Automated BIM Model-vs-Specification Compliance Engine")
st.caption("Improved original IFC/PDF + Neo4j + Gemini workflow, with project-independent matching safeguards.")
st.caption(APP_VERSION)
st.warning("Evidence-based research prototype. An IFC model and PDF may describe different projects. "
           "Automatic document relevance is not proof of contractual applicability, and no overall safety or compliance certification is provided.")


def secret(key):
    try:
        return (os.environ.get(key) or str(st.secrets.get(key, "") or "")).strip()
    except Exception:
        return (os.environ.get(key) or "").strip()


def extract_file(data, query):
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as f:
            f.write(data)
            path = f.name
        return extract_all_ifc_wall_dimensions(path, query)
    finally:
        if path:
            try: os.remove(path)
            except OSError: pass


def graph_lookup(model_hash, rows, ranked_links=()):
    from ifc_to_neo4j import IFCGraphMapper
    mapper = IFCGraphMapper()
    try:
        # Rank by PDF-to-IFC relevance first, then fill diverse IFC evidence.
        # Bound free-tier calls without hiding which elements were selected.
        limited = select_graph_elements(rows, ranked_links, cap=40)
        uploaded = mapper.upload_elements(model_hash, limited)
        found = mapper.retrieve_element_neighborhood(
            [r["GlobalId"] for r in limited], model_hash, limit=40)
        by_id = {str(g.get("globalId")): g for g in found}
        # Neo4j ORDER BY GlobalId does not represent retrieval relevance.
        ordered = [by_id[e["GlobalId"]] for e in limited if e["GlobalId"] in by_id]
        return ordered, uploaded
    finally:
        mapper.close()


def table_and_export(rows):
    data = pd.DataFrame(rows)
    if data.empty:
        st.info("No elements extracted for the selected filter.")
        return
    categories = sorted(data["IssueCategory"].dropna().unique().tolist())
    selected = st.multiselect("Filter by audit category", categories, default=categories)
    visible = data[data["IssueCategory"].isin(selected)] if selected else data
    if "ReviewPriority" in visible.columns:
        priorities = sorted(visible["ReviewPriority"].dropna().unique().tolist())
        selected_priorities = st.multiselect("Filter by review priority (not safety severity)", priorities, default=priorities)
        visible = visible[visible["ReviewPriority"].isin(selected_priorities)] if selected_priorities else visible
    cols = ["GlobalId", "ElementName", "IFCType", "Measurement", "MeasuredValue_mm", "MeasurementSource",
            "RequiredThickness_mm", "ThicknessDifference_mm", "IssueCategory", "ReviewPriority", "EvidenceReference", "Explanation"]
    st.dataframe(visible[cols].style.map(lambda v: f"background-color: {issue_colour(str(v))}", subset=["IssueCategory"]),
                 use_container_width=True, hide_index=True, height=420)
    one, two = st.columns(2)
    with one:
        st.download_button("⬇️ All IFC evidence (CSV)", data.to_csv(index=False).encode("utf-8-sig"),
                           "ifc_evidence_all.csv", "text/csv")
    with two:
        st.download_button("⬇️ Filtered IFC evidence (CSV)", visible.to_csv(index=False).encode("utf-8-sig"),
                           "ifc_evidence_filtered.csv", "text/csv")
    st.download_button("⬇️ Colour-coded evidence report (HTML)",
                       colour_report_html(visible.to_dict("records"), title="IFC Evidence Review"),
                       "ifc_evidence_colour_report.html", "text/html")


with st.sidebar:
    st.header("⚙️ Inputs and tests")
    ifc_upload = st.file_uploader("Any IFC2x3/IFC4 model", type=["ifc"])
    pdf_upload = st.file_uploader("Any searchable technical-specification PDF", type=["pdf"])
    component = st.text_input("IFC elements to extract", value="Wall",
        help="All model elements, Wall, Beam, Slab, Column, Door, Window, Roof, or a comma-separated IFC class list e.g. IfcWall,IfcDoor")
    st.caption("No sample IFC filename, GlobalId, country or building code is assumed.")
    st.subheader("1. Evaluation mode")
    mode = st.radio("Mode", ["Evidence extraction only", "Controlled synthetic test", "Verified contractual rule"])
    rule = None
    rule_error = ""
    metric = "Wall thickness"
    reference_text, tol_text, scope_name, scope_filter, gid, material_text, citation = "", "0", "One exact GlobalId", "", "", "", ""
    confirmed = False
    if mode != "Evidence extraction only":
        metric = st.selectbox("Property to compare", list(MEASUREMENT_TYPES))
        reference_text = st.text_input("Required value (mm) — enter YOUR value", placeholder="e.g., 250")
        tol_text = st.text_input("Allowed tolerance ±mm (0 if none)", value="0")
        options = ["One exact GlobalId", "Element name contains...", "External flag=True"]
        if mode == "Controlled synthetic test":
            options.append("ALL compatible elements (synthetic only)")
        scope_name = st.selectbox("Confirmed rule scope", options)
        if scope_name == "One exact GlobalId":
            gid = st.text_input("Exact IFC GlobalId", placeholder="Paste a real GlobalId from your model")
        elif scope_name == "Element name contains...":
            scope_filter = st.text_input("Name contains")
        material_text = st.text_input("Optional required material terms, comma separated", value="")
        citation = st.text_input("Verified PDF page / clause OR synthetic test reference",
                                 placeholder="Example: PDF page 15, clause 2.2")
        if mode == "Verified contractual rule":
            confirmed = st.checkbox("I independently checked the document belongs to this project AND this clause applies to these elements")
        else:
            st.info("Synthetic threshold tests prove software behaviour only, not real contractual compliance.")
    st.subheader("2. Optional modules")
    with_graph = st.checkbox("Retrieve model-isolated Neo4j graph evidence", value=False)
    use_llm = st.checkbox("Gemini — suggest PDF clauses (unverified)", value=False)
    llm_provider = "Gemini"
    llm_model = "gemini-2.5-flash"
    prompt_variant = next(iter(PROMPT_VARIANTS))
    if use_llm:
        llm_provider = st.selectbox("LLM provider", list(PROVIDER_MODELS))
        llm_model = st.selectbox("LLM model", PROVIDER_MODELS[llm_provider])
        prompt_variant = st.selectbox("Prompt version", list(PROMPT_VARIANTS))
        if not secret(SECRETS[llm_provider]):
            st.error("Add " + SECRETS[llm_provider] + " to Streamlit Secrets or disable the LLM.")
    seed = st.number_input("Validation sampling seed", min_value=1, max_value=9999999, value=2026, step=1)
    run = st.button("🚀 Analyse uploaded files", type="primary", use_container_width=True)

if run:
    if not ifc_upload or not pdf_upload:
        st.error("Upload both an IFC model and a searchable PDF.")
    elif use_llm and not secret(SECRETS[llm_provider]):
        st.error(SECRETS[llm_provider] + " missing. Add the secret or disable the LLM.")
    elif mode == "Verified contractual rule" and not confirmed:
        st.error("Confirm project/document/rule scope independently first, or choose Evidence extraction only.")
    else:
        try:
            if mode != "Evidence extraction only":
                try:
                    reference = float(reference_text.strip())
                    tolerance = float(tol_text.strip())
                except (TypeError, ValueError):
                    raise ValueError("Enter your numeric requirement and tolerance in millimetres.")
                scope = {"One exact GlobalId":"global_id", "Element name contains...":"name_contains",
                         "External flag=True":"external", "ALL compatible elements (synthetic only)":"all"}[scope_name]
                rule = AuditRule(thickness_mm=reference, tolerance_mm=tolerance, scope=scope,
                                 name_contains=scope_filter, global_id=gid,
                                 required_materials=tuple(x.strip() for x in material_text.split(",") if x.strip()),
                                 source=citation.strip(), test_mode=mode=="Controlled synthetic test", metric=metric)
            b_ifc, b_pdf = ifc_upload.getvalue(), pdf_upload.getvalue()
            model_hash, pdf_hash = hashlib.sha256(b_ifc).hexdigest(), hashlib.sha256(b_pdf).hexdigest()
            with st.spinner("Extracting IFC elements and PDF candidate evidence..."):
                elements = extract_file(b_ifc, component)
                actual_classes = sorted({e["Type"] for e in elements})
                candidates, keyword_hits = clause_candidates(b_pdf, actual_classes or component)
                assembly_reqs = find_wall_assembly_specifications(b_pdf)
                ranked_links = rank_element_requirement_candidates(
                    elements, assembly_reqs, max_pairs=80)
                all_elements = extract_file(b_ifc, "All model elements")
                all_rows = audit_elements(all_elements, None)
                mixed_sample = sample_from_current_model(all_rows, n=min(30,len(all_rows)),seed=int(seed))
                mixed_worksheet = evidence_review_worksheet(mixed_sample)
                top_candidate_review = link_review_worksheet(mixed_sample,ranked_links)
            rows = audit_elements(elements, rule)
            with st.spinner("Linking uploaded IFC GlobalIds to PDF evidence..."):
                element_links = link_pdf_evidence(b_pdf, elements)
            pdf_page_count = len(PdfReader(io.BytesIO(b_pdf)).pages)
            graph, graph_count, graph_error = [], 0, ""
            if with_graph and elements:
                with st.spinner("Neo4j: persisting and retrieving project-specific evidence..."):
                    try:
                        graph, graph_count = graph_lookup(model_hash, elements, ranked_links)
                    except Exception as exc:
                        graph_error = f"{type(exc).__name__}: {exc}"
            llm_output, llm_error, prompt_hash = "", "", ""
            llm_model_used, llm_fallback_used, llm_attempts = None, False, 0
            if use_llm:
                # Rank thickness-specific wall evidence first, independent of PDF page order.
                ai_candidates = sorted(candidates, key=lambda c: (
                    not bool(wall_thickness_references_mm(c.get("Text", ""))),
                    -int(c.get("Score", 0)), int(c.get("Page", 0))
                ))[:25]
                excerpts = candidates_text(ai_candidates)
                selected_graph = json.dumps(graph[:8], ensure_ascii=False, default=str)
                anchored = format_grounded_link_context(ranked_links, graph, max_links=8)
                prompt = prompt_for(", ".join(actual_classes), excerpts, prompt_variant,
                    selected_graph + "\nPDF-to-specific-GlobalId candidate evidence (unverified):\n" + anchored)
                prompt_hash = prompt_sha256(prompt)
                with st.spinner(f"{llm_provider}: suggesting traceable clauses (no compliance verdict)..."):
                    try:
                        llm_response = run_evidence_model(llm_provider, secret(SECRETS[llm_provider]), prompt, llm_model)
                        llm_output = llm_response["text"]
                        llm_model_used = llm_response["model_used"]
                        llm_fallback_used = llm_response["fallback_used"]
                        llm_attempts = llm_response["attempt_count"]
                    except Exception as exc:
                        llm_error = f"{type(exc).__name__}: {exc}"
            st.session_state["v4_report"] = {
                "ifc_name": ifc_upload.name, "pdf_name": pdf_upload.name, "classes": actual_classes,
                "elements": elements, "rows": rows, "candidates": candidates, "hit_count":keyword_hits,
                "element_links": element_links, "pdf_page_count": pdf_page_count,
                "assembly_reqs": assembly_reqs, "ranked_links": ranked_links,
                "mixed_worksheet": mixed_worksheet, "link_review_worksheet": top_candidate_review,
                "graph":graph,"graph_count":graph_count,"graph_error":graph_error,
                "gemini_text":llm_output,"gemini_error":llm_error,
                "llm_provider":llm_provider if use_llm else None,
                "gemini_model":llm_model if use_llm else None,
                "gemini_model_used":llm_model_used,"gemini_fallback_used":llm_fallback_used,
                "gemini_attempts":llm_attempts,
                "prompt_variant":prompt_variant if use_llm else None,"prompt_hash":prompt_hash,
                "IFC_SHA256":model_hash,"PDF_SHA256":pdf_hash,"mode":mode,"sampling_seed":int(seed),
                "graph_requested":with_graph,"gemini_requested":use_llm,"version":APP_VERSION,
                "created_utc":datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            st.error(f"Run could not complete: {type(exc).__name__}: {exc}")

result = st.session_state.get("v4_report")
if result:
    st.header("📊 Evidence and controlled results")
    rows, elements = result["rows"], result["elements"]
    counts = categories_summary(rows)
    wall_count = sum(e["Type"] in MEASUREMENT_TYPES["Wall thickness"] for e in elements)
    wall_unknown = sum(e["Type"] in MEASUREMENT_TYPES["Wall thickness"] and not isinstance(e.get("Width"), (int,float)) for e in elements)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("IFC elements",len(rows))
    c2.metric("Wall thickness unresolved",f"{wall_unknown}/{wall_count}")
    c3.metric("Discrepancies (scoped rule only)",sum(counts.get(c,0) for c in ("GEOMETRY_MISMATCH","MATERIAL_MISMATCH","MISMATCH_BOTH")))
    c4.metric("Not assessable/out of scope",sum(counts.get(c,0) for c in ("NOT_ASSESSABLE","NOT_APPLICABLE","SCOPE_UNVERIFIED")))
    st.caption("Classes in this IFC selection: " + (", ".join(result["classes"]) or "None"))
    if result["mode"] == "Evidence extraction only":
        st.info("No PASS/FAIL claim is made without a verified applicable rule.")
    elif result["mode"] == "Controlled synthetic test":
        st.warning("SYNTHETIC TEST: observed mismatch does not establish real contract non-compliance.")
    else:
        st.warning("User-verified rule comparison only. Other requirements and structural safety remain unassessed.")
    st.write("**Result categories:**", counts)
    with st.expander("🧪 Supervisor demonstration: synthetic classification categories"):
        st.warning("SYNTHETIC TEST DATA ONLY. Eight invented elements demonstrate the software classifications. These are NOT contractual evidence, real IFC results, or measured validation accuracy.")
        demo_rows = synthetic_classification_examples()
        demonstration = pd.DataFrame(demo_rows)
        st.write("**Synthetic categories:**",demonstration["IssueCategory"].value_counts().to_dict())
        st.dataframe(demonstration[["GlobalId","ObservedThickness_mm","ObservedMaterials",
                                   "RequiredThickness_mm","IssueCategory","ReviewPriority",
                                   "TruthProvenance"]].style.map(
                          lambda v: f"background-color: {issue_colour(str(v))}",
                          subset=["IssueCategory"]),
                     hide_index=True,use_container_width=True)
        st.download_button("⬇️ Download controlled synthetic classification (CSV)",
                           demonstration.to_csv(index=False).encode("utf-8-sig"),
                           "SYNTHETIC_only_classification_demonstration.csv","text/csv")
    table_and_export(rows)
    st.subheader("🏗️ Assembly requirements vs observed wall thickness — evidence only")
    st.caption("Entire PDF is searched automatically. No Gemini or Neo4j call. Numeric similarity is NOT contractual applicability and the 10 mm discovery window is NOT a permitted tolerance.")
    assembly_rows = result.get("assembly_reqs", [])
    if assembly_rows:
        st.write(f"**{len(assembly_rows)} potential overall cavity-wall/facing-masonry assembly references found in the full PDF.**")
        assembly_df = pd.DataFrame(assembly_rows)
        st.dataframe(assembly_df[["PDFPage","AssemblyThickness_mm","AssemblyKind",
                                   "QuotedLine","ContractualApplicability"]],
                     hide_index=True, use_container_width=True)
        st.download_button("⬇️ Export source assembly clauses (CSV)",
                           assembly_df.to_csv(index=False).encode("utf-8-sig"),
                           "unverified_wall_assembly_specs.csv", "text/csv")
        selected_assembly_index = st.selectbox(
            "Inspect one PDF assembly reference (not a verified rule)",
            list(range(len(assembly_rows))),
            format_func=lambda i: f"PDF page {assembly_rows[i]['PDFPage']}: {assembly_rows[i]['AssemblyThickness_mm']:g} mm — {assembly_rows[i]['AssemblyKind']}",
            key="assembly_selected_index"
        )
        selected_assembly = assembly_rows[selected_assembly_index]
        candidates_numeric = numerical_wall_assembly_neighbours(elements, selected_assembly, window_mm=10.0)
        st.write(f"**{len(candidates_numeric)} observed IFC walls with numerically similar thickness values (within 10 mm; discovery only).**")
        if candidates_numeric:
            neighbour_df = pd.DataFrame(candidates_numeric)
            st.dataframe(neighbour_df[["GlobalId","WallName","ObservedIFC_mm","PDFNominalAssembly_mm",
                                       "SignedNumericalDifference_mm","IFCMaterialLayers","ComplianceVerdict"]],
                         hide_index=True,use_container_width=True)
            st.download_button("⬇️ Export numeric-only IFC/PDF comparison (CSV)",
                               neighbour_df.to_csv(index=False).encode("utf-8-sig"),
                               "ifc_pdf_assembly_numeric_only_NOT_ASSESSABLE.csv","text/csv")
        st.warning("The PDF describes a wall ASSEMBLY. The model's wall width might describe a single MATERIAL LAYER. Confirm the original project agreement, component composition, wall location and application conditions before any contractual PASS/FAIL.")
    else:
        st.info("No explicit overall cavity-wall assembly phrase found; any numeric rule remains unverified.")

    st.subheader("🎯 Element-specific PDF-to-IFC candidates (ranked, unverified)")
    st.caption("Each candidate contains an actual IFC GlobalId, PDF page, contextual reasons, IFC materials/storey and explicit uncertainty. Ranking helps retrieval, NOT compliance classification. Neo4j is queried for relevant selected elements, not simply the first 40.")
    ranked_pairs = result.get("ranked_links", [])
    if ranked_pairs:
        ranked_df = pd.DataFrame(ranked_pairs)
        st.write("**Source-to-element screening categories:**", ranked_df["ScreeningStatus"].value_counts().to_dict())
        st.dataframe(ranked_df[[
            "PDFPage","RequirementID","GlobalId","ElementName","ObservedThickness_mm",
            "PDFNominalAssembly_mm","RankScore","ScreeningStatus","Reasons",
        ]], hide_index=True, use_container_width=True, height=320)
        st.download_button("⬇️ Download element-specific ranked source links (CSV)",
                           ranked_df.to_csv(index=False).encode("utf-8-sig"),
                           "element_specific_ranked_links_UNVERIFIED.csv","text/csv")
        st.warning("A ranked IFC/PDF pair remains NOT_ASSESSABLE until contract applicability, wall build-up, DPC/storey scope and tolerances are independently verified.")
    else:
        st.info("No explicit assembly requirements and element candidates found in this PDF/model pair.")

    st.subheader("🔗 Individual IFC-to-PDF candidate links")
    links = result.get("element_links", [])
    direct = sum(x["EvidenceLevel"]=="EXACT_GLOBALID_CANDIDATE" for x in links)
    st.caption(f"{direct} exact-GlobalId PDF candidate(s), {len(links)-direct} type-level candidate(s). "
               "These are literal identifier/class matches only, not semantic links. See the unverified wall-group screening below.")
    if links:
        link_table = pd.DataFrame(links)
        with st.expander(f"Review traceable PDF passages ({len(links)} candidates)"):
            st.dataframe(link_table,hide_index=True,use_container_width=True)
        st.download_button("⬇️ Download element-to-PDF candidate links (CSV)",
                           link_table.to_csv(index=False).encode("utf-8-sig"),
                           "element_pdf_candidate_links.csv","text/csv")

    st.subheader("🔎 Wall-to-PDF candidate screening (local, unverified)")
    st.caption("Each wall group is checked against PDF excerpts, without further Gemini calls. A candidate is NOT a validated IFC-to-contract link.")
    wall_screen = [e for e in elements if e.get("Type", "").startswith("IfcWall")]
    screening = screen_wall_clause_groups(wall_screen, result["candidates"])
    if screening:
        screened_df = pd.DataFrame(screening)
        # Display unique PDF evidence by page/text instead of overwhelming the reader
        # with every wall-type/group cross-product. Full CSV is still available.
        screening_unique = screened_df.drop_duplicates(subset=["PDFPage","CandidateText","ScreeningStatus"])
        st.write("**Candidate screening results:**", screened_df["ScreeningStatus"].value_counts().to_dict())
        st.caption(f"{len(screening_unique)} unique page/passage/status findings shown (vs {len(screened_df)} group combinations in full CSV).")
        st.dataframe(screening_unique[["PDFPage","PossibleTotalThickness_mm","SuggestedOperator","ScreeningStatus","ScreeningReason","CandidateText"]],
                     hide_index=True,use_container_width=True)
        st.download_button("⬇️ Export unverified wall–PDF screening (CSV)",
                           screened_df.to_csv(index=False).encode("utf-8-sig"),
                           "wall_pdf_screening_unverified.csv","text/csv")
    else:
        st.info("No wall-related PDF excerpts available for local clause screening.")

    st.subheader("🧱 Wall thickness clause review — single or batch")
    st.caption("All extracted walls remain in the evidence export. This local review does not make additional Gemini calls. Only PDF passages with an explicit thickness-associated dimension can be used for comparison.")
    wall_items = [e for e in elements if e.get("Type", "").startswith("IfcWall")]
    wall_candidates = wall_numeric_candidates(result["candidates"])
    if not wall_items:
        st.info("No IFC wall elements in the selected extraction.")
    elif not wall_candidates:
        st.warning("No supported TOTAL-wall thickness requirement was detected. Leaf thickness, cavity width and building height cannot be compared to overall IFC wall thickness. Inspect the original contractual specification instead of forcing a result.")
    else:
        chosen_wall_id = st.selectbox("Wall GlobalId", [e["GlobalId"] for e in wall_items],
                                     format_func=lambda gid: f"{gid} — {next((e['Name'] for e in wall_items if e['GlobalId']==gid), '')}")
        chosen_wall = next(e for e in wall_items if e["GlobalId"] == chosen_wall_id)
        st.write("**IFC evidence:**", {
            "GlobalId": chosen_wall_id, "Thickness_mm": chosen_wall.get("Width"),
            "ThicknessSource": chosen_wall.get("WidthSource"),
            "MeasurementQuality": chosen_wall.get("MeasurementQuality"),
            "MillimetresPerIFCNativeLengthUnit": chosen_wall.get("IFC_mm_per_length_unit"),
            "Materials": chosen_wall.get("Materials"),
            "ThicknessCandidates": chosen_wall.get("ThicknessCandidates"),
        })
        idx = st.selectbox("Candidate PDF passage", list(range(len(wall_candidates))),
                           format_func=lambda i: f"PDF page {wall_candidates[i]['Page']} | {wall_candidates[i]['Text'][:110]}")
        passage = wall_candidates[idx]
        st.text(passage["Text"])
        if "see para" in passage["Text"].casefold() or "diagram" in passage["Text"].casefold():
            st.warning("This short excerpt refers to other paragraphs or diagrams. Review those full source conditions before confirming the clause applies to the model.")
        context_key = f"{result['PDF_SHA256']}:{passage['Page']}"
        if st.button("📖 Show original PDF page and surrounding pages (no API cost)", key="pdf_neighbouring_context"):
            try:
                page_context = adjacent_pdf_context(pdf_upload.getvalue(), passage["Page"], radius=2)
                st.session_state["pdf_context_review"] = {"key":context_key,"text":page_context}
            except Exception as exc:
                st.error(f"Could not extract adjacent PDF pages: {type(exc).__name__}: {exc}")
        pdf_context = st.session_state.get("pdf_context_review")
        if pdf_context and pdf_context.get("key") == context_key:
            with st.expander("Full surrounding PDF context (requires independent scope review)", expanded=True):
                st.text(pdf_context["text"])
        options = wall_thickness_references_mm(passage["Text"])
        st.caption("Candidates for TOTAL wall thickness only. Requirements for individual leaves, cavity widths, insulation layers, or building-height limits are not offered for this measurement.")
        chosen_value = st.selectbox("Contractual thickness value (mm) — independently identify", options)
        hint = comparison_hint(passage["Text"])
        if hint:
            st.info(f"Source-language clue: this excerpt describes a {hint.upper()} limit. Confirm against the entire clause and its scope before any comparison.")
        else:
            st.warning("The excerpt does not establish a clear minimum or maximum. Check the full clause to determine whether it is exact, minimum or maximum.")
        directions = ["minimum", "maximum", "equal"] if hint == "minimum" else (
            ["maximum", "minimum", "equal"] if hint == "maximum" else
            ["equal", "minimum", "maximum"])
        direction = st.selectbox("Meaning of verified clause (must agree with the source)", directions,
                                 format_func=lambda x: {"equal":"Exact / nominal", "minimum":"At least (minimum)", "maximum":"At most (maximum)"}[x])
        allowed = st.number_input("Verified permitted tolerance (mm)", min_value=0.0, value=0.0, step=0.1)
        selection_mode = st.radio("Apply the reviewer-verified clause to", [
            "Selected wall only", "Same IFC type and material (candidate group)",
            "Manually selected GlobalIds"
        ])
        if selection_mode == "Selected wall only":
            chosen_walls = [chosen_wall]
        elif selection_mode == "Same IFC type and material (candidate group)":
            chosen_walls = comparable_wall_group(wall_items, chosen_wall)
        else:
            selected_ids = st.multiselect("Select wall GlobalIds", [e["GlobalId"] for e in wall_items],
                                          default=[chosen_wall_id])
            ids = set(selected_ids)
            chosen_walls = [e for e in wall_items if e["GlobalId"] in ids]
        st.write(f"**Walls selected for local comparison:** {len(chosen_walls)} of {len(wall_items)}")
        st.caption("Matching wall type/material is NOT evidence that a clause covers every element. Mixed observed thicknesses are deliberately not hidden.")
        doc_ok = st.checkbox("I independently confirmed this PDF belongs to the IFC project", key="wall_doc_verified")
        clause_ok = st.checkbox("I independently verified this clause governs total wall thickness, and confirmed the wall category and exceptions", key="wall_clause_verified")
        batch_ok = len(chosen_walls) == 1 or st.checkbox(
            "I independently verified that the clause applies to EVERY wall in the selected group",
            key="wall_batch_verified")
        selection_ids = sorted(e["GlobalId"] for e in chosen_walls)
        review_key = hashlib.sha256(json.dumps({
            "ifc":result["IFC_SHA256"],"pdf":result["PDF_SHA256"],"ids":selection_ids,
            "passage":passage,"reference_mm":chosen_value,"operator":direction,"tolerance":allowed,
        },sort_keys=True,default=str).encode()).hexdigest()
        if st.button("Compare selected walls using independently verified requirement", key="compare_walls",
                     disabled=not (doc_ok and clause_ok and batch_ok and chosen_walls)):
            try:
                checked = review_wall_batch(chosen_walls,passage,chosen_value,direction,allowed,
                                            document_confirmed=doc_ok,clause_confirmed=clause_ok,
                                            batch_scope_confirmed=batch_ok)
                st.session_state["reviewed_wall_batch"] = {"key":review_key,"rows":checked}
            except ValueError as exc:
                st.error(str(exc))
        verified_batch = st.session_state.get("reviewed_wall_batch")
        if verified_batch and verified_batch.get("key")==review_key and doc_ok and clause_ok and batch_ok:
            confirmed_rows = verified_batch["rows"]
            review_df = pd.DataFrame(confirmed_rows)
            st.write("**Reviewer-confirmed, element-level outcomes:**")
            st.write(review_df["IssueCategory"].value_counts().to_dict())
            cols = ["GlobalId","ElementName","ObservedThickness_mm","RequiredThickness_mm",
                    "ComparisonOperator","IssueCategory","PDFPage","ThicknessSource"]
            st.dataframe(review_df[cols].style.map(
                lambda v: f"background-color: {issue_colour(str(v))}", subset=["IssueCategory"]),
                hide_index=True,use_container_width=True)
            st.download_button("⬇️ Export reviewer-confirmed wall comparison (CSV)",
                               review_df.to_csv(index=False).encode("utf-8-sig"),
                               "reviewed_wall_comparison.csv","text/csv")
            st.download_button("⬇️ Colour-coded reviewed wall comparison (HTML)",
                               colour_report_html(confirmed_rows,title="Reviewer-Confirmed Wall Thickness Comparison"),
                               "reviewed_wall_comparison_colour.html","text/html")
            st.caption("Comparisons are conditional on the reviewer's applicability assertions; this is not independent verification or overall project certification.")
        elif verified_batch:
            st.info("Review scope or evidence changed. Confirm applicability and run the comparison again.")

    sample = sample_from_current_model(rows, n=min(30,len(rows)), seed=result["sampling_seed"])
    sheet = evidence_review_worksheet(sample)
    st.subheader(f"🧪 This IFC's reproducible validation sample: {len(sheet)} elements")
    if len({r.get("IFCType") for r in sample}) < 2:
        st.warning("This sample contains only ONE IFC class because the extraction filter is Wall. It cannot establish performance differences across element types. Use the optional mixed-element sample below.")
    st.caption(f"Ground-truth entries completed: 0 of {len(sheet)} (new sample; labels intentionally left blank).")
    st.caption("Generated from the CURRENT uploaded IFC (not pre-stored IDs). Sampled categories are balanced where available. "
               "All contractual truth fields are blank pending an independent reviewer.")
    st.download_button("⬇️ Download current-model ground-truth worksheet (CSV)",
                       validation_csv(sheet).encode("utf-8-sig"), "ground_truth_for_uploaded_ifc.csv","text/csv")
    st.subheader("📋 Independent 30-element linkage validation")
    mixed_rows = result.get("mixed_worksheet", [])
    if mixed_rows:
        mixed_df = pd.DataFrame(mixed_rows)
        st.write("**Mixed-class sample distribution:**", mixed_df["SampleIFCType"].value_counts().to_dict())
        st.download_button("⬇️ Download mixed-class mismatch ground-truth sheet (CSV)",
                           validation_csv(mixed_rows).encode("utf-8-sig"),
                           "mixed_elements_truth_BLANK.csv", "text/csv")
    link_sample_rows = result.get("link_review_worksheet", [])
    if link_sample_rows:
        link_sample_df = pd.DataFrame(link_sample_rows)
        st.caption("A top PDF clause candidate is attached to each sampled IFC GlobalId where one was retrieved. NO automatic ground truth. For non-wall element classes the current wall-only retrieval is incomplete.")
        st.dataframe(link_sample_df[["GlobalId","SampleIFCType",
                        "CandidateRequirementID","CandidatePDFPage",
                        "PredictedTopCandidate","CandidateStatus"]],
                     hide_index=True,use_container_width=True)
        st.download_button("⬇️ Download top-1 element-to-clause review sheet (CSV)",
                           validation_csv(link_sample_rows).encode("utf-8-sig"),
                           "element_clause_top1_truth_BLANK.csv","text/csv")
        reviewed_links = st.file_uploader("Upload independently labelled top-1 review sheet (optional)",type=["csv"],key="reviewed_links")
        if reviewed_links is not None:
            try:
                reviewed_table=pd.read_csv(io.BytesIO(reviewed_links.getvalue()),dtype=str).fillna("")
                expected=set(link_sample_df["GlobalId"])
                actual=list(reviewed_table["GlobalId"])
                if len(actual)!=len(set(actual)) or set(actual)!=expected:
                    raise ValueError("The reviewed GlobalIds must match the 30 sampled IFC elements.")
                expected_predictions=dict(zip(link_sample_df["GlobalId"],link_sample_df["PredictedTopCandidate"]))
                for row in reviewed_table.to_dict("records"):
                    if str(row["PredictedTopCandidate"]) != str(expected_predictions[row["GlobalId"]]):
                        raise ValueError("Predictions were edited. Only independent ground-truth fields may change.")
                st.json(evaluate_link_review(reviewed_table.to_dict("records")))
                st.caption("Statistics measure this sample's TOP-1 retrieval, not contract compliance or full-specification recall.")
            except Exception as exc:
                st.error(f"Linkage evaluation error: {exc}")
        else:
            st.info("No independently labelled top-1 retrieval ground truth has been provided; precision/recall/F1 must remain unreported.")

    reviewed = st.file_uploader("Optional: upload manually reviewed/labelled worksheet to calculate metrics",type=["csv"],key="reviewed_truth")
    if reviewed is not None:
        try:
            table = pd.read_csv(io.BytesIO(reviewed.getvalue()),dtype=str).fillna("")
            verified = table[table["verified_document_applies"].str.strip().str.lower().isin(["yes","true","1"])]
            metrics = evaluate_records(verified.to_dict("records"))
            st.write("**Evaluation on confirmed applicable and fully-labelled elements only:**",metrics)
            st.caption("These metrics exclude abstentions and cannot prove population-wide or cross-project performance.")
        except Exception as exc:
            st.error(f"Could not evaluate human review CSV: {exc}")

    with st.expander(f"📄 PDF evidence candidates ({result['hit_count']} hits; {len(result['candidates'])} selected)"):
        st.text(candidates_text(result["candidates"]) or "No class-relevant PDF fragments found.")
    if result["graph_error"]:
        st.error("Neo4j connection/query error: " + result["graph_error"])
    if result["graph_requested"]:
        st.caption(f"Neo4j graph elements uploaded: {result['graph_count']}; neighbours retrieved: {len(result['graph'])}. "
                   "For free-tier testing, at most 40 IFC elements are selected by source relevance then diversity. Full IFC evidence remains available.")
    if result["graph"]:
        with st.expander(f"🕸️ Neo4j evidence from this IFC hash ({len(result['graph'])} records)"):
            st.dataframe(pd.DataFrame(result["graph"]),hide_index=True,use_container_width=True)
    if result["gemini_error"]:
        st.error("Gemini request error: " + result["gemini_error"])
    if result["gemini_requested"]:
        st.subheader("🧠 LLM-suggested PDF clauses — unverified")
        st.caption(f"Provider: {result.get('llm_provider')} | Requested model: {result['gemini_model']} | Actual model: {result.get('gemini_model_used') or 'unavailable'} | Variant: {result['prompt_variant']} | Prompt SHA-256: {result['prompt_hash']}")
        if result.get("gemini_fallback_used"):
            st.warning("Primary Gemini model was temporarily unavailable; alternate model produced this candidate evidence. The actual model is recorded for repeatability.")
        st.text(result["gemini_text"] or "No response available")
    if result["gemini_requested"]:
        st.subheader("🔁 Supervisor experiment — Prompt A/B repeatability")
        st.caption("Optional: 4 LLM calls (A twice, B twice) using the SAME IFC/PDF/graph evidence. "
                   "API usage charges may apply. Similarity is NOT ground-truth accuracy.")
        if st.button("Run two repeats of BOTH prompts and save full outputs",key="repeatability"):
            runs=[]
            graph_context=json.dumps(result["graph"][:8],ensure_ascii=False,default=str)
            graph_context += "\nUnverified element-specific candidate pairs:\n" + format_grounded_link_context(result.get("ranked_links", []),result["graph"],max_links=8)
            pages=set(range(1,result["pdf_page_count"]+1))
            for variant in PROMPT_VARIANTS:
                relevant = sorted(result["candidates"], key=lambda c: (
                    not bool(wall_thickness_references_mm(c.get("Text", ""))),
                    -int(c.get("Score", 0)), int(c.get("Page", 0))
                ))[:25]
                p=prompt_for(", ".join(result["classes"]),candidates_text(relevant),variant,graph_context)
                for repeat in (1,2):
                    with st.spinner(f"Prompt {variant}, repeat {repeat}/2..."):
                        try:
                            response=run_evidence_model(result["llm_provider"],secret(SECRETS[result["llm_provider"]]),p,result["gemini_model"])
                            entry=record_output(variant,repeat,result["gemini_model"],response["model_used"],
                                                prompt_sha256(p),response["text"],pages)
                        except Exception as exc:
                            entry=record_output(variant,repeat,result["gemini_model"],"",prompt_sha256(p),"",
                                                pages,f"{type(exc).__name__}: {exc}")
                        runs.append(entry)
            st.session_state["ab_repeatability"]={
                 "IFC_SHA256":result["IFC_SHA256"],"PDF_SHA256":result["PDF_SHA256"],
                 "records":runs,"summary":summarise_repeats(runs)}
        experiment=st.session_state.get("ab_repeatability")
        if experiment and experiment["IFC_SHA256"]==result["IFC_SHA256"] and experiment["PDF_SHA256"]==result["PDF_SHA256"]:
            st.json(experiment["summary"])
            st.download_button("⬇️ Download A/B full repeated responses (JSON)",
                 json.dumps(experiment,indent=2,ensure_ascii=False),
                 "prompt_ab_repeatability_full.json","application/json")
            st.caption("Independent reviewer ground truth is needed for match precision and recall.")

    metadata = {k: result[k] for k in ("version","created_utc","IFC_SHA256","PDF_SHA256","mode","classes",
                       "graph_requested","graph_count","graph_error","gemini_requested","gemini_model",
                       "prompt_variant","prompt_hash","gemini_error","sampling_seed","llm_provider",
                       "gemini_model_used","gemini_fallback_used","gemini_attempts")}
    metadata["graph_retrieved_rows"] = len(result["graph"])
    metadata["element_specific_unverified_pairs"] = len(result.get("ranked_links", []))
    metadata["mixed_class_sample_size"] = len(result.get("mixed_worksheet", []))
    metadata["top_candidate_review_size"] = len(result.get("link_review_worksheet", []))
    metadata["independent_link_ground_truth_available"] = False
    metadata["graph_selection_strategy"] = "PDF-relevance-first with diverse IFC fill (40 cap)"
    metadata["ranked_pair_compliance_verdict"] = "NOT_ASSESSABLE"
    metadata["full_pdf_assembly_candidates"] = len(assembly_rows)
    metadata["full_pdf_assembly_pages"] = sorted({int(x["PDFPage"]) for x in assembly_rows})
    metadata["assembly_contractual_scope_verified"] = False
    metadata["numerical_proximity_is_compliance"] = False

    metadata["wall_screening_counts"] = (
        pd.DataFrame(screening)["ScreeningStatus"].value_counts().to_dict()
        if screening else {}
    )
    metadata["wall_comparison_scope"] = "TOTAL_WALL_THICKNESS_ONLY"
    metadata["local_group_screening_requires_api_call"] = False

    metadata["gemini_output_available"] = bool(result["gemini_text"])
    st.download_button("⬇️ Research reproducibility metadata (JSON)",json.dumps(metadata,indent=2),
                       "audit_run_metadata_v4.json","application/json")
    st.caption("NO automatic APPROVED/FAILED verdict. A second independent IFC test is needed to establish interoperability beyond the tested model.")
else:
    st.info("Upload your own IFC and PDF, then start with Evidence extraction only. This app contains no model-specific sample IDs or mandatory dimensions.")
