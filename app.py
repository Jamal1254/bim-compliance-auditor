"""BIM Compliance Auditor — supervisor review v2.

Clear separation of IFC extraction, evidence discovery and user-confirmed
numerical tests. The AI NEVER issues the engineering compliance verdict.
"""
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from audit_engine import AuditRule, audit_elements, categories_summary, issue_colour, numeric_width
from check_ifc_compliance import extract_all_ifc_wall_dimensions
from spec_context import clause_candidates, candidates_text
from llm_assistance import PROMPT_VARIANTS, prompt_for, prompt_sha256, candidate_clauses

APP_VERSION = "Supervisor Revision v2.0"
st.set_page_config(page_title="BIM Compliance Auditor — v2", page_icon="🏗️", layout="wide")
st.title("🏗️ BIM Model ↔ Specification Evidence Auditor")
st.caption(f"{APP_VERSION} • Separate IFC observations, unverified PDF evidence and reproducible rule tests")
st.warning(
    "Research prototype — no automatic construction approval. The uploaded IFC and specification "
    "may concern different buildings. Unless you confirm scope and an exact clause, results remain NOT ASSESSABLE."
)


def read_secret(key):
    try:
        return str(os.environ.get(key) or st.secrets.get(key, "") or "").strip()
    except Exception:
        return str(os.environ.get(key, "") or "").strip()


def _extract(file_bytes, keyword):
    name = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as f:
            f.write(file_bytes)
            name = f.name
        return extract_all_ifc_wall_dimensions(name, keyword)
    finally:
        if name and os.path.exists(name):
            os.remove(name)


def _graph_context(file_bytes, global_ids):
    name = None
    try:
        from ifc_to_neo4j import IFCGraphMapper
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as f:
            f.write(file_bytes)
            name = f.name
        mapper = IFCGraphMapper()
        try:
            mapper.upload_ifc_to_graph(name)
            return mapper.retrieve_element_neighborhood(global_ids[:150], limit=150)
        finally:
            mapper.close()
    finally:
        if name and os.path.exists(name):
            os.remove(name)


def _display_rows(rows):
    table = pd.DataFrame(rows)
    categories = sorted(table["IssueCategory"].dropna().unique().tolist())
    selected = st.multiselect("Filter by issue category", categories, default=categories)
    filtered = table[table["IssueCategory"].isin(selected)]
    st.caption("One row per IFC GlobalId. Coloured labels indicate checking priority, not structural hazard severity.")
    show_columns = ["GlobalId", "ElementName", "IFCType", "ObservedThickness_mm", "ThicknessSource",
                    "RequiredThickness_mm", "ThicknessDifference_mm", "IssueCategory", "EvidenceReference", "Explanation"]
    st.dataframe(
        filtered[show_columns].style.map(lambda val: f"background-color: {issue_colour(str(val))}", subset=["IssueCategory"]),
        use_container_width=True, hide_index=True, height=min(700, max(220, len(filtered) * 35 + 75))
    )
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ All element results (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                           "element_evidence_audit_all.csv", "text/csv")
    with c2:
        st.download_button("⬇️ Filtered results (CSV)", filtered.to_csv(index=False).encode("utf-8-sig"),
                           "element_evidence_audit_filtered.csv", "text/csv")


with st.sidebar:
    st.header("⚙️ Test configuration")
    ifc_upload = st.file_uploader("IFC model", type=["ifc"])
    spec_upload = st.file_uploader("Technical specification PDF", type=["pdf"])
    keyword = st.text_input("IFC component type", value="Wall")
    st.subheader("1. Evaluation mode")
    mode = st.radio("Mode", ["Evidence extraction only", "Controlled synthetic test", "Verified contractual rule"],
                    help="Synthetic tests cannot establish actual construction compliance.")
    verified_rule = mode != "Evidence extraction only"
    required = 352.0
    tolerance = 0.0
    scope = "external"
    substring = ""
    material_terms = ""
    reference = ""
    applicability_confirmed = False
    if verified_rule:
        required = st.number_input("Required thickness (mm)", min_value=0.01, value=352.0, step=0.1)
        tolerance = st.number_input("Allowed tolerance ±mm", min_value=0.0, value=0.0, step=0.1)
        choices = ["External flag=True", "Element name contains..."]
        if mode == "Controlled synthetic test":
            choices.append("ALL extracted elements (synthetic only)")
        scope_name = st.selectbox("Rule applies to", choices)
        scope = {"External flag=True": "external", "Element name contains...": "name_contains",
                 "ALL extracted elements (synthetic only)": "all"}[scope_name]
        if scope == "name_contains":
            substring = st.text_input("Name includes", value="")
        material_terms = st.text_input("Required material keywords (optional)", value="",
                                       help="Comma-separated tokens. Plain text match only; not semantic material verification.")
        reference = st.text_input("Exact clause / test reference",
                                  value="Controlled probe: 352 mm" if mode == "Controlled synthetic test" else "",
                                  help="For verified rules cite the applicable specification and page number.")
        if mode == "Verified contractual rule":
            applicability_confirmed = st.checkbox(
                "I independently verified the contract applies to this model AND the clause applies to the selected element scope"
            )
        else:
            st.info("Controlled tests check software behaviour only — NOT contractual compliance.")
    st.subheader("2. Optional tools")
    with_graph = st.checkbox("Retrieve graph neighbours from Neo4j (slower)", value=False)
    use_llm = st.checkbox("Use Gemini for candidate PDF clauses", value=False)
    llm_model = "gemini-2.5-flash"
    llm_variant = list(PROMPT_VARIANTS)[0]
    if use_llm:
        llm_model = st.selectbox("LLM model", ["gemini-2.5-flash", "gemini-2.0-flash"])
        llm_variant = st.selectbox("Prompt variant", list(PROMPT_VARIANTS))
        if not read_secret("GEMINI_API_KEY"):
            st.error("Add GEMINI_API_KEY in Streamlit Secrets to use Gemini.")
    run = st.button("🚀 Run evidence audit", type="primary", use_container_width=True)

if run:
    if not ifc_upload or not spec_upload:
        st.error("Upload both the IFC model and the specification PDF.")
    elif mode == "Verified contractual rule" and not applicability_confirmed:
        st.error("Contractual verdicts require explicit independent applicability confirmation.")
    elif verified_rule and not reference.strip():
        st.error("Provide a precise clause/page reference or synthetic test reference.")
    elif use_llm and not read_secret("GEMINI_API_KEY"):
        st.error("Provide GEMINI_API_KEY in Secrets or turn off optional Gemini.")
    else:
        try:
            rule = None
            if verified_rule:
                rule = AuditRule(
                    thickness_mm=float(required), tolerance_mm=float(tolerance),
                    scope=scope, name_contains=substring,
                    required_materials=tuple(x.strip() for x in material_terms.split(",") if x.strip()),
                    source=reference.strip(), test_mode=mode == "Controlled synthetic test"
                )
            ifc_bytes = ifc_upload.getvalue()
            pdf_bytes = spec_upload.getvalue()
            with st.spinner("Extracting IFC elements and locating relevant PDF evidence..."):
                elements = _extract(ifc_bytes, keyword)
                candidates, total_candidates = clause_candidates(pdf_bytes, keyword)
            if not elements:
                st.warning("No matching IFC entities were found. Check the IFC component filter.")
            else:
                graph = []
                graph_error = ""
                if with_graph:
                    with st.spinner("Retrieving IFC graph context..."):
                        try:
                            graph = _graph_context(ifc_bytes, [x["GlobalId"] for x in elements])
                        except Exception as ex:
                            graph_error = f"Neo4j retrieval unavailable: {type(ex).__name__}: {ex}"
                rows = audit_elements(elements, rule)
                llm_output = ""
                prompt_hash = ""
                if use_llm:
                    # Human review is still required even if the LLM cites a real PDF page.
                    graph_text = json.dumps(graph[:12], ensure_ascii=False, default=str)
                    prompt = prompt_for(keyword, candidates_text(candidates), llm_variant, graph_text)
                    prompt_hash = prompt_sha256(prompt)
                    with st.spinner("Gemini: finding candidate clauses (NOT issuing a verdict)..."):
                        try:
                            llm_output = candidate_clauses(read_secret("GEMINI_API_KEY"), prompt, llm_model)
                        except Exception as ex:
                            llm_output = f"Gemini request unavailable: {type(ex).__name__}: {ex}"
                st.session_state["revision_v2_results"] = {
                    "rows": rows, "elements": elements, "candidates": candidates,
                    "total_candidates": total_candidates, "graph": graph,
                    "graph_error": graph_error, "llm_output": llm_output,
                    "prompt_hash": prompt_hash, "llm_model": llm_model,
                    "llm_variant": llm_variant, "mode": mode,
                    "IFC_SHA256": hashlib.sha256(ifc_bytes).hexdigest(),
                    "PDF_SHA256": hashlib.sha256(pdf_bytes).hexdigest(),
                    "audit_input_signature": (ifc_upload.name, spec_upload.name, keyword),
                }
        except ValueError as exc:
            st.error(f"Rule/configuration error: {exc}")
        except Exception as exc:
            st.exception(exc)

report = st.session_state.get("revision_v2_results")
if report:
    st.subheader("📊 Model evidence & rule test results")
    summary = categories_summary(report["rows"])
    n = len(report["rows"])
    count_missing = sum(numeric_width(x) is None for x in report["elements"])
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("IFC entities extracted", n)
    k2.metric("Width not resolved", count_missing)
    k3.metric("Discrepancies (if rule applies)", sum(summary.get(c, 0) for c in
              ("GEOMETRY_MISMATCH", "MATERIAL_MISMATCH", "MISMATCH_BOTH")))
    k4.metric("Not assessed / out of scope", summary.get("NOT_ASSESSABLE", 0) + summary.get("NOT_APPLICABLE", 0) + summary.get("SCOPE_UNVERIFIED", 0))
    if report["mode"] == "Evidence extraction only":
        st.info("No numerical compliance decision was made. All rows are NOT ASSESSABLE until an independently confirmed rule is provided.")
    elif report["mode"] == "Controlled synthetic test":
        st.warning("CONTROLLED TEST RESULTS ONLY — discrepancies do not constitute building non-compliance.")
    else:
        st.warning("Verified-rule check only. This is not a comprehensive contract or structural safety approval.")
    st.write("**Category counts:**", summary)
    _display_rows(report["rows"])

    with st.expander(f"📄 PDF candidate clauses ({report['total_candidates']} keyword hits; {len(report['candidates'])} selected)"):
        st.caption("Candidate evidence only. PDF page numbers include the cover page. Verify clause applicability manually.")
        st.text(candidates_text(report["candidates"]))
    if report["graph_error"]:
        st.warning(report["graph_error"])
    if report["graph"]:
        with st.expander(f"🕸️ Retrieved Neo4j graph context ({len(report['graph'])} rows)"):
            st.dataframe(pd.DataFrame(report["graph"]), hide_index=True, use_container_width=True)
    if report["llm_output"]:
        st.subheader("🧠 AI-suggested specification evidence (unverified)")
        st.caption(f"Model {report['llm_model']} | {report['llm_variant']} | Prompt SHA256: {report['prompt_hash']}")
        st.text(report["llm_output"])
    st.download_button(
        "⬇️ Download research run metadata (JSON)",
        json.dumps({k: report[k] for k in ("mode", "IFC_SHA256", "PDF_SHA256", "prompt_hash", "llm_model", "llm_variant")}, indent=2),
        "audit_run_metadata.json", "application/json"
    )
    st.caption("No overall APPROVED / REVISION REQUIRED verdict is produced automatically. Independent ground-truth validation remains necessary.")
else:
    st.info("Upload your IFC and PDF in the sidebar. Start with 'Evidence extraction only' to inspect the model safely.")
