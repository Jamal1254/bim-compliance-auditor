import csv
import io
import os
import tempfile
from collections import defaultdict
from check_ifc_compliance import extract_all_ifc_wall_dimensions
from google import genai
from google.genai import types
from pypdf import PdfReader
import streamlit as st

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="BIM Hybrid Auditor", page_icon="🏗️", layout="wide"
)
st.title("🏗️ Automated BIM Model-vs-Specification Compliance Engine")
st.markdown("""
This deployment executes automated batch verification of **3D BIM schemas** against targeted semantic contexts extracted from **Technical Project Specifications** utilizing a dual **Graph-RAG** network pathway.
""")

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ Audit Parameters")

    # 1. API Key Authorization Check
    configured_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get(
        "GEMINI_API_KEY", ""
    )

    if configured_key:
        st.success("🔒 API Key Loaded Securely From Server Profile")
        gemini_key = configured_key.strip()
    else:
        raw_gemini_key = st.text_input(
            "🔑 Paste Gemini API Key",
            type="password",
            help="Provide a key if it is not configured on your server.",
        )
        gemini_key = raw_gemini_key.strip() if raw_gemini_key else ""

    st.subheader("📁 1. Upload 3D BIM Model")
    ifc_file = st.file_uploader("Upload .ifc file", type=["ifc"])
    search_keyword = st.text_input("BIM Component Type to Audit", value="Wall")

    st.subheader("📄 2. Upload Technical Specification")
    pdf_file = st.file_uploader("Upload Contract/Standard PDF", type=["pdf"])

    st.divider()
    run_audit = st.button(
        "🚀 Run Batch Compliance Audit", use_container_width=True
    )


# ---------------------------------------------------------------------------
# Spec-text extraction helpers
# ---------------------------------------------------------------------------

# Keep these terms specific to technical wall-construction content. Broad,
# very common words ("wall", "mm", "specification") were removed - they
# matched almost every paragraph in a typical construction PDF, which
# silently defeated the "not enough matches -> fall back to fuller context"
# logic below (the fallback branch was effectively unreachable).
SPEC_SEARCH_TERMS_BASE = [
    "thickness",
    "width",
    "cavity",
    "insulation",
    "external",
    "structural",
    "cladding",
    "u-value",
    "party wall",
    "separating wall",
    "building regulations",
    "fire rating",
    "blockwork",
    "masonry",
]

MIN_CHUNK_LEN = 40           # ignore fragments too short to be a real clause
MAX_CHUNK_CHARS = 14000      # rough context budget for the prompt
MIN_MATCHED_CHUNKS = 3       # below this, fall back to fuller page context


def chunk_page_text(text):
    """Split page text into paragraph-like chunks.

    Prefer blank-line paragraph breaks, since splitting a clause across
    single lines (which is how many PDF extractors wrap text) tends to
    separate a value like '110mm' from the wall type it describes. Only
    fall back to single-newline splitting if the page has no blank lines
    at all, so we don't end up with one giant undifferentiated blob.
    """
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paras) <= 1:
        paras = [p.strip() for p in text.split("\n") if p.strip()]
    return paras


def extract_spec_context(pdf_file, search_keyword):
    """Return (targeted_spec_context, matched_chunk_count) from the PDF."""
    search_terms = [search_keyword.lower()] + SPEC_SEARCH_TERMS_BASE

    reader = PdfReader(pdf_file)
    matched_chunks = []
    full_pages = []  # (page_num, text) for pages containing any search term

    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if not text:
            continue

        page_has_match = False
        for para in chunk_page_text(text):
            low = para.lower()
            if len(para) > MIN_CHUNK_LEN and any(term in low for term in search_terms):
                matched_chunks.append(f"[Page {page_num}]: {para}")
                page_has_match = True

        if page_has_match:
            full_pages.append((page_num, text.strip()))

    if len(matched_chunks) >= MIN_MATCHED_CHUNKS:
        context = "\n\n".join(matched_chunks)
    elif full_pages:
        # Too few clause-level matches to trust the narrow view - fall back
        # to the full text of every page that had at least one hit, so the
        # model sees complete clauses instead of isolated fragments.
        context = "\n\n".join(
            f"--- Page {n} ---\n{t}" for n, t in full_pages
        )
    else:
        context = "No explicitly matching spec clauses isolated."

    if len(context) > MAX_CHUNK_CHARS:
        context = context[:MAX_CHUNK_CHARS] + "\n\n[...context truncated to fit budget...]"

    return context, len(matched_chunks)


with col2:
    st.header("📊 Live Compliance Audit Report")

    if run_audit:
        if not ifc_file or not pdf_file or not gemini_key:
            st.error(
                "⚠️ Please provide all files and ensure the Gemini API Key is available."
            )
        else:
            # === STEP 1: CONTRACT SPECIFICATION EXTRACTION ===
            with st.spinner("📄 Extracting technical contract clauses..."):
                try:
                    targeted_spec_context, matched_count = extract_spec_context(
                        pdf_file, search_keyword
                    )
                except Exception as e:
                    st.error(f"Failed to process PDF text: {e}")
                    targeted_spec_context = "No explicitly matching spec clauses isolated."
                    matched_count = 0

            # === STEP 2: WRITE IFC TO A TEMP FILE ONCE ===
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".ifc"
            ) as tmp_file:
                tmp_file.write(ifc_file.getvalue())
                tmp_file_path = tmp_file.name

            # === STEP 3: BATCH IFC DATA EXTRACTION ===
            with st.spinner(
                f"📦 Parsing ALL 3D geometry properties for '{search_keyword}'..."
            ):
                all_walls_data = extract_all_ifc_wall_dimensions(
                    tmp_file_path, search_keyword
                )

            # === STEP 4: PRE-GROUP DATA & GRAPH SYNCHRONIZATION ===
            if all_walls_data:
                st.success(
                    f"✅ Extracted {len(all_walls_data)} '{search_keyword}'"
                    " instances from IFC Model"
                )

                # --- GRAPH-RAG BACKEND SYNCHRONIZATION ---
                # Reuse the temp file already written above instead of
                # writing the same IFC bytes to disk a second time.
                with st.spinner(
                    "⛓️ Synchronizing All IFC Elements into Neo4j Knowledge Graph..."
                ):
                    try:
                        from ifc_to_neo4j import IFCGraphMapper

                        mapper = IFCGraphMapper()
                        mapper.clear_database()
                        mapper.upload_ifc_to_graph(tmp_file_path)

                        st.sidebar.success(
                            "📊 Neo4j Graph Synchronized Successfully!"
                        )
                    except Exception as g_err:
                        st.sidebar.warning(
                            f"⚠️ Neo4j Sync Bypassed: {g_err}"
                        )

                # --- FULL DATA EXPORT (completeness check) ---
                # The narrative report below groups and summarizes these
                # elements for the LLM, and LLMs can silently drop or merge
                # categories when asked to "keep it concise." This CSV has
                # every single extracted element, ungrouped, so you can
                # always verify the report accounts for everything that was
                # actually found - don't rely on the markdown table alone
                # for completeness.
                csv_buffer = io.StringIO()
                csv_fields = [
                    "GlobalId", "Name", "Type", "Storey",
                    "Width", "CavityWidth", "IsExternal", "Materials",
                ]
                writer = csv.DictWriter(csv_buffer, fieldnames=csv_fields)
                writer.writeheader()
                for w in all_walls_data:
                    row = {k: w.get(k, "") for k in csv_fields}
                    row["Materials"] = "; ".join(w.get("Materials", []))
                    writer.writerow(row)

                st.download_button(
                    label=f"⬇️ Download all {len(all_walls_data)} extracted elements (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name="extracted_elements_full.csv",
                    mime="text/csv",
                )
                st.caption(
                    "The AI report below groups elements into categories for"
                    " readability and may not list every one individually -"
                    " use this CSV to verify all extracted elements are"
                    " accounted for."
                )

                # Group walls by Name and Type in Python to optimize prompt space
                grouped_walls = defaultdict(list)
                for w in all_walls_data:
                    key = f"{w['Name']} ({w['Type']})"
                    grouped_walls[key].append(w)

                wall_summary_text = ""
                for idx, (group_name, items) in enumerate(grouped_walls.items(), 1):
                    sample = items[0]
                    mats_str = (
                        ", ".join(sample["Materials"])
                        if sample["Materials"]
                        else "No associated materials populated"
                    )
                    sample_gids = ", ".join([x["GlobalId"] for x in items[:2]])
                    if len(items) > 2:
                        sample_gids += f" (+{len(items)-2} more)"

                    wall_summary_text += (
                        f"CATEGORY #{idx}: {group_name}\n"
                        f"- Total Count: {len(items)}\n"
                        f"- Sample Global IDs: {sample_gids}\n"
                        f"- Model Thickness: {sample['Width']} mm\n"
                        f"- Cavity Width: {sample['CavityWidth']} mm\n"
                        f"- Is External: {sample['IsExternal']}\n"
                        f"- Storey: {sample['Storey']}\n"
                        f"- Materials: {mats_str}\n\n"
                    )

                # UI Expander for Extracted Specs
                with st.expander(
                    f"🔍 View Isolated Semantic Spec Text Chunks ({matched_count} clause matches)"
                ):
                    st.text(targeted_spec_context)

                # === STEP 5: HYBRID LLM BATCH AUDIT WITH LAB MATRIX ===
                with st.spinner(
                    "🧠 AI Cross-Examining IFC Wall Properties Against Contract Specifications..."
                ):
                    try:
                        client = genai.Client(api_key=gemini_key)

                        system_instruction = (
                            "You are a Senior Structural and BIM Compliance Auditor. "
                            "Your job is to cross-examine extracted IFC wall geometry against the provided Contract Specification PDF. "
                            "Generate a concise, well-structured compliance report. Use a compact lab-style matrix "
                            "to compare actual model values directly against contract requirements. "
                            "If the provided contract text genuinely does not specify a value, say so plainly rather than guessing."
                        )

                        # Gemini 2.5 Flash supports up to 65,536 output
                        # tokens (the old 8,192 cap was from a smaller/older
                        # model and silently truncated large reports, e.g.
                        # once wall categories multiplied past ~6-7).
                        # It's also a "thinking" model by default, whose
                        # internal reasoning draws from the SAME token
                        # budget as the visible answer - left unchecked,
                        # that can eat the whole budget and leave
                        # response.text empty. We disable thinking here
                        # since a structured compliance table doesn't need
                        # chain-of-thought reasoning to fill in.
                        gen_config = types.GenerateContentConfig(
                            max_output_tokens=32768,
                            temperature=0.1,
                            system_instruction=system_instruction,
                            thinking_config=types.ThinkingConfig(thinking_budget=0),
                        )
                        # Gemini 2.0 Flash (the fallback below) isn't a
                        # thinking model and its config shape differs
                        # slightly, so build it without thinking_config.
                        gen_config_fallback = types.GenerateContentConfig(
                            max_output_tokens=32768,
                            temperature=0.1,
                            system_instruction=system_instruction,
                        )

                        prompt = (
                            "Execute a complete Model-versus-Contract Specification Compliance Audit:\n\n"
                            "--- CONTRACT SPECIFICATION PDF TEXT ---\n"
                            f"{targeted_spec_context}\n\n"
                            "--- EXTRACTED IFC MODEL WALL DATA ---\n"
                            f"{wall_summary_text}\n\n"
                            "INSTRUCTIONS TO PREVENT TRUNCATION:\n"
                            "- Maintain concise, clear analysis.\n"
                            "- Group similar wall types into consolidated rows in the Executive Compliance Matrix table.\n\n"
                            "REQUIRED REPORT SECTIONS:\n\n"
                            "1. 📊 EXECUTIVE COMPLIANCE MATRIX:\n"
                            "   Generate a Markdown table formatted like a laboratory test report. It MUST have these exact columns:\n"
                            "   | Wall Category / Type | Element Count | IFC Model Thickness | Contract Spec Required Thickness | IFC Model Materials | Contract Spec Required Materials | Compliance Status |\n"
                            "   - Compare IFC values side-by-side with contract PDF requirements.\n"
                            "   - Mark status as PASS, FAIL, or MISSING DATA.\n\n"
                            "2. 📄 CONTRACT SPECIFICATION REQUIREMENTS:\n"
                            "   List key clauses, dimensions, R-values, threshold insulation, and material requirements extracted from the PDF.\n\n"
                            "3. 🔍 GEOMETRIC & SPECIFICATION DISCREPANCIES:\n"
                            "   Summarize all major non-compliance issues and missing model data concisely using bullet points.\n\n"
                            "4. 🛠️ ACTIONABLE CORRECTION INSTRUCTIONS:\n"
                            "   Provide direct step-by-step guidance for the BIM Coordinator referencing key Global IDs.\n\n"
                            "5. 🏛️ FORMAL AUDIT VERDICT:\n"
                            "   State the final approval state (APPROVED or REVISION REQUIRED) inside a Markdown blockquote card."
                        )

                        try:
                            response = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=prompt,
                                config=gen_config,
                            )
                        except Exception:
                            response = client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=prompt,
                                config=gen_config_fallback,
                            )

                        # response.text can raise, or come back empty, if the
                        # response was blocked or truncated - handle that
                        # explicitly instead of letting st.markdown crash.
                        try:
                            report_text = response.text
                        except Exception:
                            report_text = None

                        finish_reason = None
                        try:
                            finish_reason = response.candidates[0].finish_reason
                        except Exception:
                            pass

                        if not report_text:
                            st.error(
                                "❌ The AI returned no usable text (finish_reason:"
                                f" {finish_reason}). This can happen if the response"
                                " was blocked or truncated - try again or reduce"
                                " the amount of input data."
                            )
                        else:
                            finish_reason_name = getattr(finish_reason, "name", str(finish_reason))
                            if finish_reason_name == "MAX_TOKENS":
                                st.warning(
                                    "⚠️ This report was cut off before finishing"
                                    " - the model ran out of output budget partway"
                                    " through (large model with many wall"
                                    " categories). The content below is real but"
                                    " incomplete; consider narrowing the search"
                                    " keyword to audit fewer categories at once,"
                                    " or re-running."
                                )
                            st.markdown(report_text)

                    except Exception as e:
                        st.error(
                            f"❌ Hybrid AI Analysis Failed. Check API Key. Error: {e}"
                        )
            else:
                st.warning(
                    f"⚠️ No elements matching '{search_keyword}' were found in the uploaded IFC file."
                )

            # === STEP 6: CLEAN UP TEMP FILE (single write, single delete) ===
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
