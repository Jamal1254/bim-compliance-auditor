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
from spec_context import clause_candidates, candidates_text
from llm_assistance import PROMPT_VARIANTS, prompt_for, prompt_sha256, candidate_clauses
from validation_export import sample_from_current_model, evidence_review_worksheet, validation_csv
from validation import evaluate_records

APP_VERSION = "Supervisor Revision v4.0 — General IFC/PDF"
st.set_page_config(page_title="BIM Evidence Auditor v4", page_icon="🏗️", layout="wide")
st.title("🏗️ BIM ↔ Technical Specification Evidence Auditor")
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
        limited = rows[:300]  # honest partial graph cap for large IFC uploads
        uploaded = mapper.upload_elements(model_hash, limited)
        return mapper.retrieve_element_neighborhood([r["GlobalId"] for r in limited], model_hash, limit=150), uploaded
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
    cols = ["GlobalId", "ElementName", "IFCType", "Measurement", "MeasuredValue_mm", "MeasurementSource",
            "RequiredThickness_mm", "ThicknessDifference_mm", "IssueCategory", "EvidenceReference", "Explanation"]
    st.dataframe(visible[cols].style.map(lambda v: f"background-color: {issue_colour(str(v))}", subset=["IssueCategory"]),
                 use_container_width=True, hide_index=True, height=420)
    one, two = st.columns(2)
    with one:
        st.download_button("⬇️ All IFC evidence (CSV)", data.to_csv(index=False).encode("utf-8-sig"),
                           "ifc_evidence_all.csv", "text/csv")
    with two:
        st.download_button("⬇️ Filtered IFC evidence (CSV)", visible.to_csv(index=False).encode("utf-8-sig"),
                           "ifc_evidence_filtered.csv", "text/csv")


with st.sidebar:
    st.header("⚙️ Inputs and tests")
    ifc_upload = st.file_uploader("Any IFC2x3/IFC4 model", type=["ifc"])
    pdf_upload = st.file_uploader("Any searchable technical-specification PDF", type=["pdf"])
    component = st.text_input("IFC elements to extract", value="All model elements",
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
            graph, graph_count, graph_error = [], 0, ""
            if with_graph and elements:
                with st.spinner("Neo4j: persisting and retrieving project-specific evidence..."):
                    try:
                        graph, graph_count = graph_lookup(model_hash, elements)
                    except Exception as exc:
                        graph_error = f"{type(exc).__name__}: {exc}"
            llm_output, llm_error, prompt_hash = "", "", ""
            if use_llm:
                excerpts = candidates_text(candidates)
                selected_graph = json.dumps(graph[:12], ensure_ascii=False, default=str)
                prompt = prompt_for(", ".join(actual_classes), excerpts, prompt_variant, selected_graph)
                prompt_hash = prompt_sha256(prompt)
                with st.spinner("Gemini: suggesting traceable clauses (no compliance verdict)..."):
                    try:
                        llm_output = candidate_clauses(secret("GEMINI_API_KEY"), prompt, llm_model)
                    except Exception as exc:
                        llm_error = f"{type(exc).__name__}: {exc}"
            st.session_state["v4_report"] = {
                "ifc_name": ifc_upload.name, "pdf_name": pdf_upload.name, "classes": actual_classes,
                "elements": elements, "rows": rows, "candidates": candidates, "hit_count":keyword_hits,
                "graph":graph,"graph_count":graph_count,"graph_error":graph_error,
                "gemini_text":llm_output,"gemini_error":llm_error,"gemini_model":llm_model if use_llm else None,
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

    sample = sample_from_current_model(rows, n=min(30,len(rows)), seed=result["sampling_seed"])
    sheet = evidence_review_worksheet(sample)
    st.subheader(f"🧪 This IFC's reproducible validation sample: {len(sheet)} elements")
    st.caption("Generated from the CURRENT uploaded IFC (not pre-stored IDs). Sampled categories are balanced where available. "
               "All contractual truth fields are blank pending an independent reviewer.")
    st.download_button("⬇️ Download current-model ground-truth worksheet (CSV)",
                       validation_csv(sheet).encode("utf-8-sig"), "ground_truth_for_uploaded_ifc.csv","text/csv")
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
                   "For large models only the first 300 sorted elements are graphed in this prototype.")
    if result["graph"]:
        with st.expander(f"🕸️ Neo4j evidence from this IFC hash ({len(result['graph'])} records)"):
            st.dataframe(pd.DataFrame(result["graph"]),hide_index=True,use_container_width=True)
    if result["gemini_error"]:
        st.error("Gemini request error: " + result["gemini_error"])
    if result["gemini_requested"]:
        st.subheader("🧠 Gemini-suggested PDF clauses — unverified")
        st.caption(f"Model: {result['gemini_model']} | Variant: {result['prompt_variant']} | Prompt SHA-256: {result['prompt_hash']}")
        st.text(result["gemini_text"] or "No response available")
    metadata = {k: result[k] for k in ("version","created_utc","IFC_SHA256","PDF_SHA256","mode","classes",
                       "graph_requested","graph_count","graph_error","gemini_requested","gemini_model",
                       "prompt_variant","prompt_hash","gemini_error","sampling_seed")}
    metadata["graph_retrieved_rows"] = len(result["graph"])
    metadata["gemini_output_available"] = bool(result["gemini_text"])
    st.download_button("⬇️ Research reproducibility metadata (JSON)",json.dumps(metadata,indent=2),
                       "audit_run_metadata_v4.json","application/json")
    st.caption("NO automatic APPROVED/FAILED verdict. A second independent IFC test is needed to establish interoperability beyond the tested model.")
else:
    st.info("Upload your own IFC and PDF, then start with Evidence extraction only. This app contains no model-specific sample IDs or mandatory dimensions.")
