# BIM Hybrid Auditor — supervisor fix (20 October 2026)

This branch starts from the original main commit and improves its IFC upload → IfcOpenShell → PDF extraction → Neo4j → Gemini workflow. The original main branch is untouched.

## Fixes
- Parse IFC2x3 / IFC4 classes and native project units, not test filenames or specific countries
- No fixed GlobalIds, 352 mm default, sample-specific materials or categories in regular processing
- One evidence row per IFC GlobalId; wall measurements distinguished from door/window dimensions
- Require user-specified verified rule, scope, tolerance and PDF citation before numerical PASS/FAIL
- Missing, ambiguous and conflicting model values are shown for review rather than fabricated
- Graph nodes are keyed by the uploaded IFC SHA256 to isolate unrelated projects; no hardcoded credentials or global deletes
- Gemini retrieves page-referenced candidate clauses, not an unsupported engineering certification
- Generate a reproducible 30-element sample from EACH uploaded IFC, with ground truth left blank

## Streamlit test
Create a new Streamlit app from branch original-code-supervisor-fix-2026-10-20 and main file app.py. In Secrets, add GEMINI_API_KEY, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD and NEO4J_DATABASE. Rotate the previously exposed database password.

First test evidence-only with any IFC and searchable PDF, then separately enable Neo4j and Gemini, then try a completely different IFC/PDF pair. Scanned image-only PDFs need OCR. The app cannot guarantee compliance for every jurisdiction or document without human-confirmed applicability.

## Verification
20 local tests passed using simulated IFC2x3 and IFC4 models with imperial and metric unit declarations. End-to-end live Streamlit tests on the new branch and independent project generalisation are still needed.
