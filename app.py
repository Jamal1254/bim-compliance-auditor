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
from llm_assistance import PROMPT_VARIANTS, prompt_for, prompt_sha256, candidate_clauses_with_status
from validation_export import sample_from_current_model, evidence_review_worksheet, validation_csv
from validation import evaluate_records
from evidence_linking import link_pdf_evidence
from wall_focus import wall_numeric_candidates, wall_thickness_references_mm, comparable_wall_group, review_wall_batch, screen_wall_clause_groups, comparison_hint
from reporting import colour_report_html
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


def graph_lookup(model_hash, rows):
    from ifc_to_neo4j import IFCGraphMapper
    mapper = IFCGraphMapper()
    try:
        limited = rows[:40]  # free-tier-friendly bounded graph subset; stable GlobalId ordering
        uploaded = mapper.upload_elements(model_hash, limited)
        return mapper.retrieve_element_neighborhood([r["GlobalId"] for r in limited], model_hash, limit=40), uploaded
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
    llm_model = "gemini-2.5-flash"
    prompt_variant = next(iter(PROMPT_VARIANTS))
    if use_llm:
        llm_model = st.selectbox("LLM", ["gemini-2.5-flash", "gemini-2.0-flash"])
        prompt_variant = st.selectbox("Prompt version", list(PROMPT_VARIANTS))
        if not secret("GEMINI_API_KEY"):
            st.error("Add GEMINI_API_KEY to Streamlit Secrets or disable Gemini.")
    seed = st.number_input("Validation sampling seed", min_value=1, max_value=9999999, value=2026, step=1)
    run = st.button("🚀 Analyse uploaded files", type="primary", use_container_width=True)

if run:
    if not ifc_upload or not pdf_upload:
        st.error("Upload both an IFC model and a searchable PDF.")
    elif use_llm and not secret("GEMINI_API_KEY"):
        st.error("Gemini API key missing. Add secret or disable Gemini.")
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
            rows = audit_elements(elements, rule)
            with st.spinner("Linking uploaded IFC GlobalIds to PDF evidence..."):
                element_links = link_pdf_evidence(b_pdf, elements)
            pdf_page_count = len(PdfReader(io.BytesIO(b_pdf)).pages)
            graph, graph_count, graph_error = [], 0, ""
            if with_graph and elements:
                with st.spinner("Neo4j: persisting and retrieving project-specific evidence..."):
                    try:
                        graph, graph_count = graph_lookup(model_hash, elements)
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
                prompt = prompt_for(", ".join(actual_classes), excerpts, prompt_variant, selected_graph)
                prompt_hash = prompt_sha256(prompt)
                with st.spinner("Gemini: suggesting traceable clauses (no compliance verdict)..."):
                    try:
                        llm_response = candidate_clauses_with_status(secret("GEMINI_API_KEY"), prompt, llm_model)
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
                "graph":graph,"graph_count":graph_count,"graph_error":graph_error,
                "gemini_text":llm_output,"gemini_error":llm_error,"gemini_model":llm_model if use_llm else None,
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
    table_and_export(rows)
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
        st.write("**Candidate screening results:**", screened_df["ScreeningStatus"].value_counts().to_dict())
        st.dataframe(screened_df[["Group","WallCount","ObservedTotalThickness_mm","PDFPage",
                                   "PossibleTotalThickness_mm","SuggestedOperator","ScreeningStatus","ScreeningReason"]],
                     hide_index=True,use_container_width=True)
        st.download_button("⬇️ Export unverified wall–PDF screening (CSV)",
                           screened_df.to_csv(index=False).encode("utf-8-sig"),
                           "wall_pdf_screening_unverified.csv","text/csv")
    else:
        st.info("No wall-related PDF excerpts available for local clause screening.")

    st.subheader("🏗️ Cavity-wall assembly specifications (full PDF search)")
    st.caption("Searches ALL PDF pages locally for explicit overall cavity-wall or facing-masonry assembly thickness. These are not yet verified IFC-to-contract links. A single 350-mm masonry layer cannot be assumed to be the same physical quantity as a multi-layer 352-mm cavity-wall assembly.")
    if st.button("Find wall-assembly specifications throughout full PDF (no API cost)", key="assembly_search"):
        try:
            assembly_found = find_wall_assembly_specifications(pdf_upload.getvalue())
            st.session_state["assembly_spec_search"] = {
                "pdf_sha": result["PDF_SHA256"], "records": assembly_found
            }
        except Exception as exc:
            st.error(f"Full PDF assembly scan failed: {type(exc).__name__}: {exc}")
    assembly_search = st.session_state.get("assembly_spec_search")
    if assembly_search and assembly_search.get("pdf_sha") == result["PDF_SHA256"]:
        assembly_rows = assembly_search["records"]
        if assembly_rows:
            assembly_df = pd.DataFrame(assembly_rows)
            st.dataframe(assembly_df[["PDFPage","AssemblyThickness_mm","AssemblyKind",
                                      "QuotedLine","ComparisonMeaning","ContractualApplicability"]],
                         hide_index=True, use_container_width=True)
            st.download_button("⬇️ Download unverified PDF assembly clauses (CSV)",
                               assembly_df.to_csv(index=False).encode("utf-8-sig"),
                               "pdf_wall_assembly_candidates_unverified.csv", "text/csv")
            st.warning("The source's assembly thickness may include separate cavity, brick and block layers; verify full scope and IFC layer composition before any element-level comparison.")
        else:
            st.info("No explicit cavity-wall assembly thickness phrases were found in this PDF.")

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
    st.subheader("📋 Mixed-element validation sample — optional, local only")
    st.caption("The supervisor requested 25–30 diverse IFC elements. This action reads all element classes from the SAME uploaded IFC without calling Gemini or Neo4j; the wall-first analysis remains unchanged.")
    if st.button("Generate 30-element mixed-class sample from this IFC (no API cost)", key="mixed_sample"):
        try:
            all_project_elements = extract_file(ifc_upload.getvalue(), "All model elements")
            all_review_rows = audit_elements(all_project_elements, None)
            mixed_sample = sample_from_current_model(all_review_rows, n=min(30,len(all_review_rows)), seed=result["sampling_seed"])
            st.session_state["mixed_ground_truth"] = {
                "ifc_hash": result["IFC_SHA256"],
                "seed": result["sampling_seed"],
                "worksheet": evidence_review_worksheet(mixed_sample),
            }
        except Exception as exc:
            st.error(f"Mixed sample failed: {type(exc).__name__}: {exc}")
    mixed = st.session_state.get("mixed_ground_truth")
    if (mixed and mixed["ifc_hash"] == result["IFC_SHA256"]
            and mixed["seed"] == result["sampling_seed"]):
        mixed_df = pd.DataFrame(mixed["worksheet"])
        st.write("**Sample class distribution:**", mixed_df["SampleIFCType"].value_counts().to_dict())
        st.download_button("⬇️ Download mixed-class ground-truth worksheet (CSV)",
                           validation_csv(mixed["worksheet"]).encode("utf-8-sig"),
                           "ground_truth_mixed_elements.csv","text/csv")
        st.caption("Independent ground truth remains BLANK. Random sampling and larger class diversity do not establish compliance or statistical accuracy.")

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
                   "For free-tier testing, only the first 40 extracted elements are graphed; full IFC evidence remains available.")
    if result["graph"]:
        with st.expander(f"🕸️ Neo4j evidence from this IFC hash ({len(result['graph'])} records)"):
            st.dataframe(pd.DataFrame(result["graph"]),hide_index=True,use_container_width=True)
    if result["gemini_error"]:
        st.error("Gemini request error: " + result["gemini_error"])
    if result["gemini_requested"]:
        st.subheader("🧠 Gemini-suggested PDF clauses — unverified")
        st.caption(f"Requested model: {result['gemini_model']} | Actual model: {result.get('gemini_model_used') or 'unavailable'} | Variant: {result['prompt_variant']} | Prompt SHA-256: {result['prompt_hash']}")
        if result.get("gemini_fallback_used"):
            st.warning("Primary Gemini model was temporarily unavailable; alternate model produced this candidate evidence. The actual model is recorded for repeatability.")
        st.text(result["gemini_text"] or "No response available")
    if result["gemini_requested"]:
        st.subheader("🔁 Supervisor experiment — Prompt A/B repeatability")
        st.caption("Optional: 4 Gemini calls (A twice, B twice) using the SAME IFC/PDF/graph evidence. "
                   "API usage charges may apply. Similarity is NOT ground-truth accuracy.")
        if st.button("Run two repeats of BOTH prompts and save full outputs",key="repeatability"):
            runs=[]
            graph_context=json.dumps(result["graph"][:8],ensure_ascii=False,default=str)
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
                            response=candidate_clauses_with_status(secret("GEMINI_API_KEY"),p,result["gemini_model"])
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
                       "prompt_variant","prompt_hash","gemini_error","sampling_seed",
                       "gemini_model_used","gemini_fallback_used","gemini_attempts")}
    metadata["graph_retrieved_rows"] = len(result["graph"])
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
