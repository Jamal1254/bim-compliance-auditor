import streamlit as st
import os
import tempfile
from pypdf import PdfReader
from check_ifc_compliance import extract_ifc_wall_dimensions

st.set_page_config(page_title="BIM Hybrid Auditor", page_icon="🏗️", layout="wide")
st.title("🏗️ Automated BIM Model-vs-Specification Compliance Engine")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ Audit Parameters")
    gemini_key = st.text_input("🔑 Paste Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    ifc_file = st.file_uploader("Upload .ifc file", type=["ifc"])
    search_keyword = st.text_input("BIM Component Type to Audit", value="Wall")
    pdf_file = st.file_uploader("Upload Contract/Standard PDF", type=["pdf"])
    run_audit = st.button("🚀 Run Hybrid Compliance Audit", use_container_width=True)

with col2:
    st.header("📊 Live Compliance Audit Report")
    if run_audit:
        if not ifc_file or not pdf_file or not gemini_key:
            st.error("⚠️ Please provide all files and the API Key.")
        else:
            relevant_chunks = []
            reader = PdfReader(pdf_file)
            search_terms = [search_keyword.lower(), "thickness", "width", "cavity", "insulation", "external", "structural"]
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    for para in text.split("\n\n"):
                        if any(term in para.lower() for term in search_terms) and len(para.strip()) > 30:
                            relevant_chunks.append(f"[Page {page_num + 1}]: {para.strip()}")
            targeted_spec_context = "\n\n".join(relevant_chunks[:30]) if relevant_chunks else "No matching clauses found."

            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_file:
                tmp_file.write(ifc_file.getvalue())
                tmp_file_path = tmp_file.name

            ifc_data = extract_ifc_wall_dimensions(tmp_file_path, search_keyword)
            try: os.unlink(tmp_file_path)
            except Exception: pass
            
            if ifc_data:
                st.success(f"✅ Exact BIM Mapping Complete: {ifc_data['Type']}")
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.metric("Thickness", f"{ifc_data['Width']} mm")
                m_col2.metric("Cavity Width", f"{ifc_data['CavityWidth']} mm" if ifc_data['CavityWidth'] else "None")
                m_col3.metric("Is External", "True" if ifc_data['IsExternal'] else "False")
                
                with st.spinner("🧠 Gemini Analyzing..."):
                    from google import genai
                    client = genai.Client(api_key=gemini_key)
                    prompt = f"Cross-examine:\nIFC METRICS:\n- Type: {ifc_data['Type']}\n- Width: {ifc_data['Width']}mm\n- External: {ifc_data['IsExternal']}\n\nSPEC TEXT:\n{targeted_spec_context}\n\nGenerate structured engineering report and end with clear COMPLIANT or NON-COMPLIANT status."
                    
                    try: response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    except Exception: response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
                    st.info(response.text)
            else:
                st.error("Component not found.")
