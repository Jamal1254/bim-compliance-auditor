"""Replaceable evidence-LLM boundary; provider may not determine BIM compliance.

Gemini is the free-tier-friendly default. OpenAI is OPTIONAL and billed through
a separate API key. Provider failures never prevent IFC/PDF evidence export.
"""
import json
from urllib import request, error
from llm_assistance import candidate_clauses_with_status, SYSTEM

PROVIDER_MODELS = {
    "Gemini": ("gemini-2.5-flash", "gemini-2.0-flash"),
    "OpenAI": ("gpt-4.1-mini", "gpt-4o-mini"),
}
SECRETS = {"Gemini": "GEMINI_API_KEY", "OpenAI": "OPENAI_API_KEY"}


def _openai_response_text(payload):
    fragments = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                fragments.append(part["text"])
    return "\n".join(fragments).strip()


def run_evidence_model(provider, api_key, prompt, model, *, opener=None):
    """Stable provider-independent response shape for repeatability experiments."""
    if provider not in PROVIDER_MODELS:
        raise ValueError("Unknown LLM provider")
    if model not in PROVIDER_MODELS[provider]:
        raise ValueError("Unsupported model selection for this provider")
    if not api_key:
        raise ValueError(f"Missing {SECRETS[provider]}")
    if provider == "Gemini":
        data = candidate_clauses_with_status(api_key, prompt, model)
        return dict(data, provider_used="Gemini")
    opener = opener or request.urlopen
    body = json.dumps({
        "model": model,
        "instructions": SYSTEM,
        "input": prompt,
        "max_output_tokens": 2800,
        "store": False,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/responses", data=body, method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type":"application/json"},
    )
    try:
        with opener(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        # Never print the API key or the raw request payload in errors/logs.
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}; check credentials, access, quota and model.") from None
    text = _openai_response_text(payload)
    return {
        "text": text if text else "No extractable candidate clause returned.",
        "provider_used": "OpenAI",
        "model_used": payload.get("model",model),
        "fallback_used": False,
        "attempt_count":1,
        "status":"success" if text else "empty_response",
    }
