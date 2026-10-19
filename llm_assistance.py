"""Optional LLM extraction of *candidate evidence*, never an audit verdict."""
import hashlib
from google import genai
from google.genai import types

PROMPT_VARIANTS = {
    "A - strict evidence": "List up to ten possible relevant clauses with their PDF page numbers. State element type, numeric requirement and qualification if available.",
    "B - conservative": "Find up to ten candidate requirements. Emphasize scope restrictions, exceptions and uncertainty. Cite PDF page numbers.",
}

SYSTEM = (
    "You are a specification evidence assistant, NOT a compliance certifier. "
    "The IFC file and PDF may belong to different projects. Output only candidate clauses "
    "grounded in the provided excerpts with [PDF page N] references. "
    "Never declare PASS, FAIL, compliant, noncompliant, approved, or revision required. "
    "Do not recommend design changes. Do not invent specification requirements. "
    "If relevant evidence is unavailable, say so."
)


def prompt_for(component, pdf_excerpt, variant, graph_excerpt=""):
    if variant not in PROMPT_VARIANTS:
        raise ValueError("Unknown prompt variant")
    return (f"Component class: {component}\n"
            f"Task: {PROMPT_VARIANTS[variant]}\n"
            "Note: contractual applicability is NOT independently established.\n\n"
            f"--- PDF EXCERPTS ---\n{pdf_excerpt[:12000]}\n\n"
            f"--- OPTIONAL GRAPH ELEMENT CONTEXT ---\n{graph_excerpt[:2400]}")


def prompt_sha256(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def candidate_clauses(api_key, prompt, model="gemini-2.5-flash"):
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.0, max_output_tokens=2500)
    response = client.models.generate_content(model=model, contents=prompt, config=config)
    out = response.text or ""
    # The LLM text is displayed as unverified candidate evidence only.
    return out.strip() or "No candidate clauses were returned."
