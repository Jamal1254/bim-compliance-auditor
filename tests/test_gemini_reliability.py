"""Gemini reliability tests using a fake provider; never use real API keys."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
import pytest

def load_llm(monkeypatch):
    google=ModuleType("google")
    genai=ModuleType("google.genai")
    genai.types=SimpleNamespace(GenerateContentConfig=lambda **k:k)
    google.genai=genai
    monkeypatch.setitem(sys.modules,"google",google)
    monkeypatch.setitem(sys.modules,"google.genai",genai)
    spec=importlib.util.spec_from_file_location("llm_under_test",Path(__file__).resolve().parents[1]/"llm_assistance.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class DummyError(Exception):
    def __init__(self,code):
        super().__init__(f"{code} UNAVAILABLE")
        self.code=code

class FakeClient:
    def __init__(self, responses):
        self.responses=iter(responses)
        self.calls=[]
        self.models=self
    def generate_content(self,model,contents,config):
        self.calls.append(model)
        result=next(self.responses)
        if isinstance(result,Exception):raise result
        return SimpleNamespace(text=result)

def test_success(monkeypatch):
    llm=load_llm(monkeypatch)
    r=llm.candidate_clauses_with_status("key","prompt",client=FakeClient(["clause [PDF page 7]"]),sleeper=lambda _:None)
    assert r["status"]=="success" and r["attempt_count"]==1
    assert r["fallback_used"] is False

def test_retry_503(monkeypatch):
    llm=load_llm(monkeypatch)
    c=FakeClient([DummyError(503),"found"])
    r=llm.candidate_clauses_with_status("key","prompt",client=c,sleeper=lambda _:None)
    assert r["attempt_count"]==2 and not r["fallback_used"]
    assert c.calls==["gemini-2.5-flash"]*2

def test_fallback_503(monkeypatch):
    llm=load_llm(monkeypatch)
    c=FakeClient([DummyError(503),DummyError(503),"fallback evidence"])
    r=llm.candidate_clauses_with_status("key","prompt",client=c,sleeper=lambda _:None)
    assert r["fallback_used"] and r["attempt_count"]==3
    assert r["model_used"]=="gemini-3.5-flash-lite"

def test_auth_not_retried(monkeypatch):
    llm=load_llm(monkeypatch)
    c=FakeClient([DummyError(401)])
    with pytest.raises(DummyError):
        llm.candidate_clauses_with_status("key","prompt",client=c,sleeper=lambda _:None)
    assert len(c.calls)==1

def test_persistent_503_fails_cleanly(monkeypatch):
    llm=load_llm(monkeypatch)
    c=FakeClient([DummyError(503)]*3)
    with pytest.raises(RuntimeError,match="temporarily unavailable"):
        llm.candidate_clauses_with_status("key","prompt",client=c,sleeper=lambda _:None)
    assert len(c.calls)==3

def test_missing_key(monkeypatch):
    llm=load_llm(monkeypatch)
    with pytest.raises(ValueError,match="missing"):
        llm.candidate_clauses_with_status("","prompt")

def test_empty_response(monkeypatch):
    llm=load_llm(monkeypatch)
    r=llm.candidate_clauses_with_status("key","prompt",client=FakeClient([""]),sleeper=lambda _:None)
    assert r["status"]=="empty_response"
