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

with col2:
    st.header("📊 Live Compliance Audit Report")

    if run_audit:
        if not ifc_file or not pdf_file or not gemini_key:
            st.error(
                "⚠️ Please provide all files and ensure the Gemini API Key is"
                " available."
            )
        else:
            # === STEP 1: TARGETED SEMANTIC TEXT RETRIEVAL ===
            relevant_chunks = []
            with st.spinner("📄 Extracting technical contract clauses..."):
                try:
                    reader = PdfReader(pdf_file)
                    search_terms = [
                        search_keyword.lower(),
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
                    ]
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            for para in text.split("\n\n"):
                                if any(
                                    term in para.lower() for term in search_terms
                                ) and len(para.strip()) > 30:
                                    relevant_chunks.append(
                                        f"[Page {page_num + 1}]:"
                                        f" {para.strip()}"
                                    )
                except Exception as e:
                    st.error(f"Failed to process PDF text: {e}")

            targeted_spec_context = (
                "\n\n".join(relevant_chunks[:35])
                if relevant_chunks
                else "No explicitly matching spec clauses isolated."
            )

            # === STEP 2: BATCH IFC DATA EXTRACTION ===
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".ifc"
            ) as tmp_file:
                tmp_file.write(ifc_file.getvalue())
                tmp_file_path = tmp_file.name

            with st.spinner(
                f"📦 Parsing ALL 3D geometry properties for '{search_keyword}'..."
            ):
                all_walls_data = extract_all_ifc_wall_dimensions(
                    tmp_file_path, search_keyword
                )

            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass

            # === STEP 3: PRE-GROUP DATA & GRAPH SYNCHRONIZATION ===
            if all_walls_data:
                st.success(
                    f"✅ Extracted {len(all_walls_data)} '{search_keyword}'"
                    " instances from IFC Model"
                )

                # --- GRAPH-RAG BACKEND SYNCHRONIZATION ---
                with st.spinner(
                    "⛓️ Synchronizing All IFC Elements into Neo4j Knowledge"
                    " Graph..."
                ):
                    try:
                        from ifc_to_neo4j import IFCGraphMapper

                        mapper = IFCGraphMapper()
                        mapper.clear_database()

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".ifc"
                        ) as graph_tmp:
                            graph_tmp.write(ifc_file.getvalue())
                            graph_tmp_path = graph_tmp.name

                        mapper.upload_ifc_to_graph(graph_tmp_path)
                        try:
                            os.unlink(graph_tmp_path)
                        except Exception:
                            pass

                        st.sidebar.success(
                            "📊 Neo4j Graph Synchronized Successfully!"
                        )
                    except Exception as g_err:
                        st.sidebar.warning(
                            f"⚠️ Neo4j Sync Bypassed: {g_err}"
                        )

                # Group walls by Name and Type in Python to minimize token footprint
                grouped_walls = defaultdict(list)
                for w in all_walls_data:
                    key = f"{w['Name']} ({w['Type']})"
                    grouped_walls[key].append(w)

                wall_summary_text = ""
                for idx, (group_name, items) in enumerate(
                    grouped_walls.items(), 1
                ):
                    sample = items[0]
                    mats_str = (
                        ", ".join(sample["Materials"])
                        if sample["Materials"]
                        else "No associated materials populated"
                    )
                    sample_gids = ", ".join([x["GlobalId"] for x in items[:3]])
                    if len(items) > 3:
                        sample_gids += f" (+{len(items)-3} more)"

                    wall_summary_text += (
                        f"CATEGORY #{idx}: {group_name}\n"
                        f"- Total Count: {len(items)}\n"
                        f"- Sample Global IDs: {sample_gids}\n"
                        f"- Model Thickness: {sample['Width']} mm\n"
                        f"- Cavity Width: {sample['CavityWidth']} mm\n"
                        f"- Is External: {sample['IsExternal']}\n"
                        f"- Materials: {mats_str}\n\n"
                    )

                # UI Expander for Extracted Specs
                with st.expander(
                    "🔍 View Isolated Semantic Spec Text Chunks"
                ):
                    st.text(targeted_spec_context)

                # === STEP 4: HYBRID LLM BATCH AUDIT GENERATION ===
                with st.spinner(
                    "🧠 Frontier AI Evaluating Summarized Categories Against PDF"
                    " Specification..."
                ):
                    try:
                        client = genai.Client(api_key=gemini_key)

                        # Strict formatting rules to prevent table line rendering loops
                        system_instruction = (
                            "You are a Lead Structural and BIM Compliance"
                            " Auditor. CRITICAL FORMATTING RULE: Keep Markdown"
                            " tables clean, concise, and short. Never generate"
                            " long repeating dashed separator lines in Markdown"
                            " tables. Keep table cell descriptions under 15"
                            " words."
                        )

                        gen_config = types.GenerateContentConfig(
                            max_output_tokens=8192,
                            temperature=0.1,
                            system_instruction=system_instruction,
                        )

                        prompt = (
                            "Cross-examine the following BIM wall categories"
                            " against the contract PDF specifications:\n\n"
                            "PRE-GROUPED BIM WALL DATA"
                            f" ({len(all_walls_data)} Total Elements across"
                            f" {len(grouped_walls)} Categories):\n"
                            f"{wall_summary_text}\n\n"
                            "CONTRACT SPECIFICATION"
                            f" CLAUSES:\n{targeted_spec_context}\n\n"
                            "REPORT SECTIONS REQUIRED:\n"
                            "1. 📊 EXECUTIVE COMPLIANCE MATRIX:\n"
                            "   Create a clean Markdown table with columns: |"
                            " Category | Count | Sample ID | Model Width | Spec"
                            " Target | Status |\n"
                            "   Keep cell text concise for proper text"
                            " wrapping.\n\n"
                            "2. 🔍 GEOMETRIC & KNOWLEDGE GRAPH ANALYSIS:\n"
                            "   Summarize overall geometric gaps, material"
                            " gaps, or unit issues across categories.\n\n"
                            "3. 📄 SPECIFICATION CLASH:\n"
                            "   Detail specific contract violations (e.g.,"
                            " party wall acoustic gaps, unapproved storefronts,"
                            " thickness errors).\n\n"
                            "4. 🛠️ ACTIONABLE BIM MODIFICATION ORDER:\n"
                            "   Provide a bulleted list of fixes for the"
                            " Revit coordinator grouped by Global ID/Category.\n\n"
                            "5. FORMAL ENGINEERING VERDICT:\n"
                            "   End with a highlighted blockquote verdict card"
                            " (e.g., > ### 🔴 VERDICT: NON-COMPLIANT)."
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
                                config=gen_config,
                            )

                        st.markdown("### 🤖 Complete Project Batch Compliance Report")
                        st.markdown(response.text)

                    except Exception as e:
                        st.error(
                            "❌ Hybrid AI Analysis Failed. Check API Key. Error:"
                            f" {e}"
                        )
            else:
                st.error(
                    "Could not find any 3D components matching the term"
                    f" '{search_keyword}' inside your uploaded IFC model file."
                )
