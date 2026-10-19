"""Gemini proposes page-referenced PDF evidence; it never certifies compliance."""
import hashlib
from google import genai
from google.genai import types

PROMPT_VARIANTS = {
    "A - strict evidence": "For each represented IFC class, propose relevant requirements. Quote only short evidence excerpts and include their precise PDF page markers. State any scope restrictions; return 'no applicable clause found' when uncertain.",
    "B - conservative": "Prioritise false-positive avoidance. For each IFC class, distinguish possible clauses from applicable ones, with scope exceptions and exact PDF page markers. Flag missing information instead of guessing.",
}
SYSTEM = (
    "You are a multilingual specification EVIDENCE RETRIEVAL assistant, not a construction certifier. "
    "Only use the supplied PDF extracts with their provided PDF page markers; never invent a clause or page. "
    "The IFC and PDF may be unrelated projects. Do NOT output PASS, FAIL, compliance approval or design changes. "
    "Return a short evidence list (element class, possible clause, numeric value if stated, units, page, "
    "scope qualifiers, why it may be relevant, missing information). "
    "Do not confuse wall thickness with beam width, curtain-wall panel width, or storey height. "
    "If the extracts are weak or unrelated, explicitly say the evidence is insufficient."
)


def prompt_for(component, pdf_excerpt, variant, graph_excerpt=""):
    if variant not in PROMPT_VARIANTS:
        raise ValueError("Unknown prompt variant")
    return ("IFC element classes actually present: " + str(component) + "\n" +
            "Task: " + PROMPT_VARIANTS[variant] + "\n" +
            "The contract's applicability has NOT been independently confirmed.\n\n" +
            "--- PDF EVIDENCE (candidate, not verified) ---\n" + (pdf_excerpt[:16000] or "No PDF candidate snippets found") +
            "\n\n--- OPTIONAL Neo4j MODEL-ISOLATED NEIGHBOURS ---\n" + graph_excerpt[:3500])


def prompt_sha256(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def candidate_clauses(api_key, prompt, model="gemini-2.5-flash"):
    if not api_key:
        raise ValueError("GEMINI_API_KEY secret is missing")
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.0, max_output_tokens=2800)
    response = client.models.generate_content(model=model, contents=prompt, config=config)
    out = response.text or ""
    if not out.strip():
        return "No extractable candidate clause returned."
    return out.strip()
