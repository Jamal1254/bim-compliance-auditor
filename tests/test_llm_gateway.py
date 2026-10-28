"""Prove switching API providers needs no IFC/Neo4j/prompt code changes."""
import json
import pytest
import llm_gateway


class FakeHTTPResponse:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):
        return json.dumps({"model":"gpt-4.1-mini","output":[
            {"type":"message","content":[{"type":"output_text","text":"PDF p.14 clause candidate; NOT verified"}]}
        ]}).encode()


def test_openai_responses_provider_adapter_is_injected_and_private():
    calls=[]
    def fake_open(req,timeout):
        calls.append((req.full_url,req.get_header("Authorization"),json.loads(req.data),timeout))
        return FakeHTTPResponse()
    out=llm_gateway.run_evidence_model("OpenAI","SECRET","PDF p.14", "gpt-4.1-mini",opener=fake_open)
    assert out["text"].startswith("PDF p.14")
    assert out["provider_used"]=="OpenAI"
    assert out["attempt_count"]==1
    assert calls[0][0]=="https://api.openai.com/v1/responses"
    assert calls[0][2]["store"] is False
    assert calls[0][2]["input"]=="PDF p.14"
    assert calls[0][3]==45


def test_gemini_adapter_preserves_provider_response(monkeypatch):
    def fake_provider(key,prompt,model):
        assert key=="key" and prompt=="prompt"
        return {"text":"PDF p.14","model_used":model,
                "attempt_count":1,"fallback_used":False,"status":"success"}
    monkeypatch.setattr(llm_gateway,"candidate_clauses_with_status",fake_provider)
    out=llm_gateway.run_evidence_model("Gemini","key","prompt","gemini-2.5-flash")
    assert out["provider_used"]=="Gemini"
    assert out["model_used"]=="gemini-2.5-flash"


def test_invalid_provider_model_and_secrets_block_requests():
    with pytest.raises(ValueError,match="Unknown"):
        llm_gateway.run_evidence_model("Unknown","key","prompt","anything")
    with pytest.raises(ValueError,match="Unsupported"):
        llm_gateway.run_evidence_model("OpenAI","key","prompt","gemini-2.5-flash")
    with pytest.raises(ValueError,match="Missing"):
        llm_gateway.run_evidence_model("OpenAI","","prompt","gpt-4.1-mini")
