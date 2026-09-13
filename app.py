import os
import tempfile
import pandas as pd
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

                # === STEP 4: HYBRID LLM BATCH AUDIT GENERATION (WALL SPECIALIZED) ===
                with st.spinner(
                    "🧠 AI Cross-Examining IFC Wall Properties Against Contract Specifications..."
                ):
                    try:
                        client = genai.Client(api_key=gemini_key)

                        # Render Native Interactive Dataframe for Wall Category Overview
                        st.markdown("### 📊 Executive Compliance Matrix (IFC Walls)")
                        matrix_rows = []
                        for group_name, items in grouped_walls.items():
                            sample = items[0]
                            mats_str = ", ".join(sample["Materials"]) if sample["Materials"] else "None"
                            sample_gids = ", ".join([x["GlobalId"] for x in items[:2]])
                            if len(items) > 2:
                                sample_gids += f" (+{len(items)-2} more)"

                            matrix_rows.append({
                                "Wall Category / Type": group_name,
                                "Element Count": len(items),
                                "Sample GlobalIDs": sample_gids,
                                "Thickness (mm)": sample["Width"],
                                "Cavity Width (mm)": sample["CavityWidth"],
                                "Is External": sample["IsExternal"],
                                "Assigned Materials": mats_str
                            })

                        df_matrix = pd.DataFrame(matrix_rows)
                        st.dataframe(df_matrix, use_container_width=True)

                        # System Instruction for Active Dynamic Cross-Examination
                        system_instruction = (
                            "You are a Senior Structural and BIM Compliance Auditor specializing in wall assemblies. "
                            "Analyze the provided IFC wall data and evaluate every single category against the contract PDF clauses. "
                            "Do not repeat the raw data. Perform dynamic engineering checks: compare numerical wall thicknesses, "
                            "cavity dimensions, external vs. internal classification, and material layers against contract requirements. "
                            "Highlight non-compliant walls clearly using bullet points."
                        )

                        gen_config = types.GenerateContentConfig(
                            max_output_tokens=8192,
                            temperature=0.1,
                            system_instruction=system_instruction,
                        )

                        prompt = (
                            "Perform an active compliance audit on these BIM wall categories against the contract PDF spec clauses:\n\n"
                            f"EXTRACTED IFC WALL DATA ({len(all_walls_data)} Total Wall Elements across {len(grouped_walls)} Categories):\n"
                            f"{wall_summary_text}\n\n"
                            f"CONTRACT SPECIFICATION CLAUSES:\n{targeted_spec_context}\n\n"
                            "REQUIRED AUDIT REPORT SECTIONS:\n"
                            "1. 🔍 GEOMETRIC & MATERIAL DISCREPANCIES:\n"
                            "   Identify specific wall categories where model thickness, cavity width, or material assignment fails to match the PDF spec requirements.\n\n"
                            "2. 📄 SPECIFICATION CLASHES & VIOLATIONS:\n"
                            "   List explicit contract violations (e.g., external wall missing required cavity thickness, wrong stud size, unassigned materials).\n\n"
                            "3. 🛠️ RESTRUCTURING & CORRECTION INSTRUCTIONS:\n"
                            "   Provide actionable instructions for the BIM Coordinator listing exact Global IDs and required model changes.\n\n"
                            "4. 🏛️ FORMAL AUDIT VERDICT:\n"
                            "   Provide the final approval state (APPROVED / REVISION REQUIRED) inside a blockquote card."
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

                        st.markdown("### 🤖 Detailed Wall Compliance Findings")
                        st.markdown(response.text)

                    except Exception as e:
                        st.error(
                            f"❌ Hybrid AI Analysis Failed. Check API Key. Error: {e}"
                        )
            else:
                st.warning(
                    f"⚠️ No elements found matching component type '{search_keyword}' in the uploaded IFC file."
                )
