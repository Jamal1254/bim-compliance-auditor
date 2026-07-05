import streamlit as st
import os
import tempfile
from pypdf import PdfReader
from check_ifc_compliance import extract_ifc_wall_dimensions

st.set_page_config(page_title="BIM Hybrid Auditor", page_icon="🏗️", layout="wide")
st.title("🏗️ Automated BIM Model-vs-Specification Compliance Engine")
st.markdown("""
This deployment executes automated verification of **3D BIM schemas** against targeted semantic contexts extracted from **Technical Project Specifications** utilizing a dual **Graph-RAG** network pathway.
""")

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ Audit Parameters")
    
    # 1. Look for a hidden environment variable or Streamlit cloud configuration secret
    configured_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
    
    # 2. Render UI condition dynamically based on authorization state
    if configured_key:
        st.success("🔒 API Key Loaded Securely From Server Profile")
        gemini_key = configured_key.strip()
    else:
        raw_gemini_key = st.text_input("🔑 Paste Gemini API Key", type="password", help="Provide a key if it is not configured on your server.")
        gemini_key = raw_gemini_key.strip() if raw_gemini_key else ""
        
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
        if not ifc_file or not pdf_file or not gemini_key:
            st.error("⚠️ Please provide all files and ensure the Gemini API Key is available.")
        else:
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
                
                # --- GRAPH-RAG BACKEND SYNCHRONIZATION ---
                with st.spinner("⛓️ Mapping IFC Structural Relationships into Neo4j Knowledge Graph..."):
                    try:
                        from ifc_to_neo4j import IFCGraphMapper
                        mapper = IFCGraphMapper()
                        mapper.clear_database()
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as graph_tmp:
                            graph_tmp.write(ifc_file.getvalue())
                            graph_tmp_path = graph_tmp.name
                        
                        mapper.upload_ifc_to_graph(graph_tmp_path)
                        try: os.unlink(graph_tmp_path)
                        except Exception: pass
                        
                        st.sidebar.success("📊 Neo4j Graph Synchronized Successfully!")
                    except Exception as g_err:
                        st.sidebar.warning(f"⚠️ Neo4j Sync Bypassed: {g_err}")

                # --- GRAPH CONTEXT RETRIEVAL (CYPHER LAYER) ---
                graph_context_str = "No connected structural topology could be fetched from the database."
                try:
                    from ifc_to_neo4j import IFCGraphMapper
                    mapper = IFCGraphMapper()
                    
                    cypher_query = """
                    MATCH (e:BIMElement {globalId: $gid})
                    OPTIONAL MATCH (e)-[:CONTAINED_IN]->(s:BuildingStorey)
                    OPTIONAL MATCH (e)-[:HAS_MATERIAL]->(m:Material)
                    RETURN s.name AS Level, collect(m.name) AS Materials
                    """
                    with mapper.driver.session(database=mapper.database) as session:
                        result = session.run(cypher_query, gid=ifc_data['GlobalId']).single()
                        if result:
                            level_name = result["Level"] if result["Level"] else "Unknown Level Structure"
                            mats = ", ".join(result["Materials"]) if result["Materials"] else "No associated materials populated"
                            graph_context_str = f"- Mapped Spatial Zone / Storey Level: {level_name}\n- Mapped Material Graph Links: {mats}"
                except Exception as graph_read_err:
                    graph_context_str = f"Graph data extraction omitted: {graph_read_err}"

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
                        
                        prompt = (
                            f"You are an expert Structural and BIM Compliance Engineer executing a rigorous architectural quality assurance audit.\n\n"
                            f"Cross-examine the following multi-layered project datasets for dimensional or regulatory mismatches:\n\n"
                            f"LAYER 1: EXACT STRUCTURED BIM METRICS (IFC Parse):\n"
                            f"- Object Architectural Type: {ifc_data['Type']}\n"
                            f"- Object Reference Name: {ifc_data['Name']}\n"
                            f"- Instance Global ID: {ifc_data['GlobalId']}\n"
                            f"- Model Described Thickness: {ifc_data['Width']}mm\n"
                            f"- Isolated Cavity Space: {ifc_data['CavityWidth'] if ifc_data['CavityWidth'] else 'not explicitly defined'}mm\n"
                            f"- External Envelope Exposure: {ifc_data['IsExternal']}\n\n"
                            f"LAYER 2: KNOWLEDGE GRAPH RELATIONAL TOPOLOGY (Neo4j Context Retrieval):\n"
                            f"{graph_context_str}\n\n"
                            f"LAYER 3: TARGETED SEMANTIC CLAUSES (Extracted Specification PDF Blocks):\n"
                            f"{targeted_spec_context}\n\n"
                            f"Instructions for Report Generation:\n"
                            f"1. 📊 EXECUTIVE COMPLIANCE MATRIX: Begin with a clean, standard Markdown table using the EXACT headers: | Parameter | IFC Value | Spec Target | Status |. CRITICAL: You must include two distinct rows for type compliance:\n"
                            f"   - Row A: 'Object Architectural Type' (Evaluate strictly if the IFC Class container, e.g. IfcWall, is the correct schema type for a wall. If yes, status is COMPLIANT).\n"
                            f"   - Row B: 'Construction Assembly Type' (Evaluate the actual building system, e.g. SIP vs Masonry Cavity, against the text spec. If they mismatch, status is CRITICAL ERROR).\n"
                            f"   - Keep all definitions in the 'Spec Target' column under 2 short sentences for clean text wrapping.\n\n"
                            f"2. 🔍 GEOMETRIC & KNOWLEDGE GRAPH ANALYSIS: Deep dive into the physical thickness metric and the graph relational context layer. Analyze if the structural connections in the network meet requirements or display major architectural data gaps.\n"
                            f"3. 📄 SPECIFICATION CLASH: Evaluate structural material alignment (e.g., using an IfcCurtainWall system where only masonry cavity or rendered blockwork assemblies are detailed).\n"
                            f"4. 🛠️ ACTIONABLE BIM MODIFICATION ORDER: Conclude with a strict, bulleted instructions list telling the Revit Modeler/BIM Coordinator exactly what properties to edit or insert to clear this flag.\n"
                            f"5. FORMAL ENGINEERING VERDICT: Formally declare an absolute engineering verdict at the very end. You must enclose the final verdict inside a markdown blockquote (e.g., '> ### 🔴 VERDICT: UNVERIFIED DUE TO DATA GAP') so that it renders as a cleanly highlighted visual card in Streamlit."
                        )
                        
                        # Structured Fallback Model Engine Routing
                        try: 
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        except Exception: 
                            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
                        
                        st.markdown("### 🤖 Hybrid Graph-RAG Compliance Report")
                        st.markdown(response.text)
                        
                    except Exception as e:
                        st.error(f"❌ Hybrid AI Analysis Failed. Please check if your Gemini API key is valid and active. Error details: {e}")
            else:
                st.error(f"Could not find any 3D component matching the term '{search_keyword}' inside your uploaded IFC model file.")

