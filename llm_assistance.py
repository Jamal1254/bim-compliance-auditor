"""Gemini proposes page-referenced PDF evidence; it never certifies compliance."""
import hashlib
import re
import time
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
    "Do not confuse wall thickness with beam width, curtain-wall panel width, storey height, or building-height thresholds such as 18 m. "
    "Internal/external status does NOT establish whether a wall is load-bearing. "
    "A referenced table without its actual numeric values is NOT a known numeric thickness requirement. "
    "A numeric dimension is only a wall thickness if the adjacent source text explicitly identifies it as such. "
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


def _temporary_service_failure(exc):
    """Retry only temporary provider-side failures; not invalid keys or quota limits."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code is not None:
        try:
            return int(code) in (502, 503, 504)
        except (TypeError, ValueError):
            pass
    return bool(re.search(r"\b(?:502|503|504)\b", str(exc)))


def candidate_clauses_with_status(api_key, prompt, model="gemini-2.5-flash", *,
                                   client=None, sleeper=None):
    """Return verified API invocation status while leaving BIM judgments untouched.

    Retry a transient 5xx once on the preferred model, then try an alternate
    Gemini model once. Authentication/quota errors fail immediately. The user
    can still download all IFC and PDF evidence when every LLM attempt fails.
    """
    if not api_key:
        raise ValueError("GEMINI_API_KEY secret is missing")
    client = client if client is not None else genai.Client(api_key=api_key)
    sleeper = sleeper if sleeper is not None else time.sleep
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM, temperature=0.0, max_output_tokens=2800
    )
    alternate = "gemini-3.5-flash-lite"
    models = [model] + ([alternate] if model != alternate else [])
    attempts = []
    last_error = None
    for index, candidate in enumerate(models):
        trials = 2 if index == 0 else 1
        for trial in range(trials):
            attempts.append(candidate)
            try:
                response = client.models.generate_content(
                    model=candidate, contents=prompt, config=config
                )
                value = (getattr(response, "text", None) or "").strip()
                if not value:
                    return {"text": "No extractable candidate clause returned.",
                            "model_used": candidate, "fallback_used": index > 0,
                            "attempt_count": len(attempts), "status": "empty_response"}
                return {"text": value, "model_used": candidate,
                        "fallback_used": index > 0,
                        "attempt_count": len(attempts), "status": "success"}
            except Exception as exc:
                if not _temporary_service_failure(exc):
                    raise
                last_error = exc
                if index == 0 and trial == 0:
                    sleeper(1)
    raise RuntimeError(
        "Gemini remains temporarily unavailable (502/503/504) after "
        "a retry and one alternate-model attempt. IFC/PDF/Neo4j evidence "
        "is unaffected. Please retry the AI analysis later."
    ) from last_error


def candidate_clauses(api_key, prompt, model="gemini-2.5-flash"):
    """Backward-compatible interface for existing calls."""
    return candidate_clauses_with_status(api_key, prompt, model)["text"]
