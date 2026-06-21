import streamlit as st
import os
import tempfile
from pypdf import PdfReader
from check_ifc_compliance import extract_ifc_wall_dimensions

st.set_page_config(page_title="BIM Hybrid Auditor", page_icon="🏗️", layout="wide")
st.title("🏗️ Automated BIM Model-vs-Specification Compliance Engine")
st.markdown("""
This deployment executes automated verification of **3D BIM schemas** against targeted semantic contexts extracted from **Technical Project Specifications**.
""")

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ Audit Parameters")
    raw_gemini_key = st.text_input("🔑 Paste Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    
    st.subheader("📁 1. Upload 3D BIM Model")
    ifc_file = st.file_uploader("Upload .ifc file", type=["ifc"])
    search_keyword = st.text_input("BIM Component Type to Audit", value="Wall")
    
    st.subheader("📄 2. Upload Technical Specification")
    pdf_file = st.file_uploader("Upload Contract/Standard PDF", type=["pdf"])
    
    st.divider()
    run_audit = st.button("🚀 Run Hybrid Compliance Audit", use_container_width=True)

with col2:
    st.header("📊 Live Compliance Audit Report")
    
    if run_audit:
        if not ifc_file or not pdf_file or not raw_gemini_key:
            st.error("⚠️ Please provide all files and the API Key.")
        else:
            # Clean the API key immediately to completely eliminate space-pasting ClientErrors
            gemini_key = raw_gemini_key.strip()
            
            # === STEP 1: TARGETED SEMANTIC TEXT RETRIEVAL ===
            relevant_chunks = []
            with st.spinner("📄 Extracting technical contract clauses..."):
                try:
                    reader = PdfReader(pdf_file)
                    search_terms = [search_keyword.lower(), "thickness", "width", "cavity", "insulation", "external", "structural", "cladding", "u-value", "building regulations"]
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            for para in text.split("\n\n"):
                                if any(term in para.lower() for term in search_terms) and len(para.strip()) > 30:
                                    relevant_chunks.append(f"[Page {page_num + 1}]: {para.strip()}")
                except Exception as e:
                    st.error(f"Failed to process PDF text: {e}")
            
            targeted_spec_context = "\n\n".join(relevant_chunks[:30]) if relevant_chunks else "No explicitly matching spec clauses isolated."

            # === STEP 2: EXACT STRUCTURED BIM EXTRACTION ===
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_file:
                tmp_file.write(ifc_file.getvalue())
                tmp_file_path = tmp_file.name

            with st.spinner(f"📦 Parsing exact 3D geometry properties for '{search_keyword}'..."):
                ifc_data = extract_ifc_wall_dimensions(tmp_file_path, search_keyword)
            
            try: 
                os.unlink(tmp_file_path)
            except Exception: 
                pass
            
            # === STEP 3: CONTEXT ASSEMBLY & DISCREPANCY AUDIT ===
            if ifc_data:
                st.success(f"✅ Exact BIM Mapping Complete: {ifc_data['Type']}")
                
                # Render Metric Cards
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.metric("Thickness / Width", f"{ifc_data['Width']} mm" if ifc_data['Width'] != 'Unknown' else "Unknown")
                m_col2.metric("Cavity Width", f"{ifc_data['CavityWidth']} mm" if ifc_data['CavityWidth'] else "None/Undefined")
                m_col3.metric("Is External Element", "True" if ifc_data['IsExternal'] else "False")
                
                # Context Layer Visibility
                with st.expander("🔍 View Isolated Semantic Spec Text Chunks"):
                    st.text(targeted_spec_context)
                
                with st.spinner("🧠 Frontier model evaluating compiled context layers..."):
                    try:
                        from google import genai
                        client = genai.Client(api_key=gemini_key)
                        
                        # Advanced Industrial Prompt Engineering Structure
                    prompt = (
                        f"You are an expert Structural and BIM Compliance Engineer executing a rigorous architectural quality assurance audit.\n\n"
                        f"Cross-examine the following project dataset layers for dimensional or regulatory mismatches:\n\n"
                        f"LAYER 1: EXACT STRUCTURED BIM METRICS (IFC Parse):\n"
                        f"- Object Architectural Type: {ifc_data['Type']}\n"
                        f"- Object Reference Name: {ifc_data['Name']}\n"
                        f"- Instance Global ID: {ifc_data['GlobalId']}\n"
                        f"- Model Described Thickness: {ifc_data['Width']}mm\n"
                        f"- Isolated Cavity Space: {ifc_data['CavityWidth'] if ifc_data['CavityWidth'] else 'not explicitly defined'}mm\n"
                        f"- External Envelope Exposure: {ifc_data['IsExternal']}\n\n"
                        f"LAYER 2: TARGETED SEMANTIC CLAUSES (Extracted Specification PDF Blocks):\n"
                        f"{targeted_spec_context}\n\n"
                        f"Instructions for Report Generation:\n"
                        f"1. 📊 EXECUTIVE COMPLIANCE MATRIX: Begin with a clean markdown summary table matching Parameter, IFC Value, Spec Target, and Status (COMPLIANT, CRITICAL ERROR, or DATA GAP). CRITICAL: Keep the descriptions in the 'Spec Target' column highly concise (maximum 1-2 short sentences) to ensure proper text-wrapping and scannability on a standard dashboard screen.\n"
                        f"2. 🔍 GEOMETRIC ANALYSIS: Deep dive into the physical thickness metric. If it reads 'Unknown', explicitly connect this data gap to an inability to assess thermal bridging, U-values, or compliance under UK Building Regulations Part L.\n"
                        f"3. 📄 SPECIFICATION CLASH: Evaluate structural material alignment (e.g., using an IfcCurtainWall system where only masonry cavity or rendered blockwork assemblies are detailed).\n"
                        f"4. 🛠️ ACTIONABLE BIM MODIFICATION ORDER: Conclude with a strict, bulleted instructions list telling the Revit Modeler/BIM Coordinator exactly what properties to edit or insert to clear this flag.\n"
                        f"5. FORMAL ENGINEERING VERDICT: Formally declare an absolute engineering verdict at the very end. You must enclose the final verdict inside a standard markdown blockquote (e.g., '> ### 🔴 VERDICT: UNVERIFIED DUE TO DATA GAP') so that it renders as a cleanly highlighted visual card in Streamlit."
                    )
                        
                        # Failsafe Routing Logic with verified model names
                        try: 
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        except Exception: 
                            response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
                        
                        st.markdown("### 🤖 Hybrid Discrepancy Audit Report")
                        st.info(response.text)
                        
                    except Exception as e:
                        st.error(f"❌ Hybrid AI Analysis Failed. Please check if your Gemini API key is valid and active. Error details: {e}")
            else:
                st.error(f"Could not find any 3D component matching the term '{search_keyword}' inside your uploaded IFC model file.")
