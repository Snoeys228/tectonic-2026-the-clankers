from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from config import get_settings
from database import get_repository
from main import app
from models import AskRequest
from services.ai_service import AIServiceError, GeminiAnswer, PayslipAssistant, unverified_amounts
from services.retrieval import resolve_periods, retrieve


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def ask(client, employee_id, question):
    response = client.post("/api/ask", json={"employee_id": employee_id, "question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["employees_loaded"] == 3
    assert body["payslips_loaded"] == 9


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Trust &amp; Transparency" in response.text or "Payslip Assistant" in response.text


def test_payslip_totals_are_consistent():
    for employee in get_repository().list_employees():
        for p in get_repository().get_payslips(employee.employee_id):
            expected = (
                p.gross_salary - p.employee_social_security + p.benefit_in_kind
                - p.withholding_tax - p.special_social_security + p.total_net_adjustments
            )
            assert p.net_pay == expected
            assert f"NET PAY: EUR {p.net_pay:,.2f}" in p.sections["net_pay"]


def test_net_pay_comparison(client):
    body = ask(client, "EMP-100234", "Why is my net pay lower this month compared to last month?")
    assert body["answer_found"] is True
    assert body["periods_considered"] == ["2026-08", "2026-09"]
    assert "2,836.60" in body["answer_summary"]
    assert "211.84" in body["answer_summary"]
    cited = [s for s in body["source_snippets"] if s["cited"]]
    assert any(s["source_id"] == "PS-202609-EMP100234#net_pay" for s in cited)
    assert all("text" in s and s["text"] for s in body["source_snippets"])


def test_vacation_days(client):
    body = ask(client, "EMP-100234", "How many vacation days do I have left?")
    assert body["answer_found"] is True
    assert "4.0 legal vacation days" in body["answer_summary"]
    assert [s["section"] for s in body["source_snippets"] if s["cited"]] == ["leave"]


def test_meal_vouchers_for_named_month(client):
    body = ask(client, "EMP-100587", "How many meal vouchers did I get in August?")
    assert body["periods_considered"] == ["2026-08"]
    assert "21 meal vouchers" in body["answer_summary"]


def test_compared_to_last_month_uses_latest_two_periods(client):
    body = ask(client, "EMP-100587", "Did my meal vouchers change compared to last month?")
    assert body["periods_considered"] == ["2026-08", "2026-09"]


def test_missing_period(client):
    body = ask(client, "EMP-100234", "What was my net pay in March 2026?")
    assert body["answer_found"] is False
    assert body["source_snippets"] == []
    assert any("March 2026" in w for w in body["warnings"])


def test_out_of_scope_question(client):
    body = ask(client, "EMP-100234", "What is the weather in Paris tomorrow?")
    assert body["answer_found"] is False
    assert body["confidence_score"] <= 0.5


@pytest.mark.parametrize(
    "question",
    ["What is my manager's salary?", "How much does my colleague Lucas earn?", "What is the average salary here?"],
)
def test_questions_about_other_people_are_refused(client, question):
    body = ask(client, "EMP-100234", question)
    assert body["answer_found"] is False
    assert body["source_snippets"] == []
    assert "own payslips" in body["answer_summary"]


def test_validation_errors(client):
    response = client.post("/api/ask", json={"employee_id": "12345", "question": "net pay?"})
    assert response.status_code == 422
    assert response.json()["error"] == "Invalid request"

    response = client.post("/api/ask", json={"employee_id": "EMP-100234", "question": "  "})
    assert response.status_code == 422


def test_unknown_employee(client):
    response = client.post("/api/ask", json={"employee_id": "EMP-999999", "question": "What is my net pay?"})
    assert response.status_code == 404
    assert response.json()["request_id"]


def test_payslip_endpoints(client):
    overview = client.get("/api/employees/EMP-100912/payslips").json()
    assert [p["period"] for p in overview] == ["2026-07", "2026-08", "2026-09"]
    text = client.get("/api/employees/EMP-100912/payslips/2026-09/text").json()
    assert "Benefit in kind company car" in text["text"]
    assert client.get("/api/employees/EMP-100912/payslips/2025-01/text").status_code == 404


def test_employees_only_see_their_own_payslips():
    payslips = get_repository().get_payslips("EMP-100234")
    result = retrieve("What is my net pay?", payslips)
    assert all(s.chunk.employee_id == "EMP-100234" for s in result.snippets)


def test_period_resolution():
    payslips = get_repository().get_payslips("EMP-100234")
    assert resolve_periods("net pay in july", payslips)[0] == ["2026-07"]
    assert resolve_periods("gross salary year to date", payslips)[0] == ["2026-07", "2026-08", "2026-09"]
    assert resolve_periods("how may I see my net pay", payslips)[0] == ["2026-09"]


def test_unverified_amounts():
    context = "NET PAY: EUR 2,836.60\nNET PAY: EUR 3,048.44"
    assert unverified_amounts("Net pay dropped by EUR 211.84 to EUR 2,836.60.", context) == []
    assert unverified_amounts("Your bonus was EUR 999.99.", context) == [Decimal("999.99")]


class _FakeModels:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return type("Response", (), {"parsed": self.result, "text": None, "candidates": [], "prompt_feedback": None})()


class _FakeClient:
    def __init__(self, models):
        self.aio = type("Aio", (), {"models": models})()


def _assistant(models, ai_mode="auto"):
    settings = replace(get_settings(), ai_mode=ai_mode, gemini_api_key="test-key")
    assistant = PayslipAssistant(replace(settings, gemini_api_key=None), get_repository())
    assistant.settings = settings
    assistant._client = _FakeClient(models)
    return assistant


@pytest.mark.anyio
async def test_gemini_rag_flow_grounds_and_validates_sources():
    models = _FakeModels(
        GeminiAnswer(
            answer="You have 4.0 legal vacation days remaining.",
            answer_found=True,
            source_ids=["PS-202609-EMP100234#leave", "PS-000000-FAKE#leave"],
            confidence=0.95,
        )
    )
    response = await _assistant(models).answer(
        AskRequest(employee_id="EMP-100234", question="How many vacation days do I have left?")
    )
    call = models.calls[0]
    assert "You are a trustworthy payroll assistant." in call["config"].system_instruction
    assert "REMAINING 4.0" in call["contents"]
    assert response.mode == "gemini"
    assert [s.source_id for s in response.source_snippets if s.cited] == ["PS-202609-EMP100234#leave"]
    assert any("unknown sources" in w for w in response.warnings)
    assert 0.9 <= response.confidence_score <= 1.0


@pytest.mark.anyio
async def test_gemini_hallucinated_figures_are_flagged():
    models = _FakeModels(
        GeminiAnswer(
            answer="Your net pay is EUR 9,999.99.",
            answer_found=True,
            source_ids=["PS-202609-EMP100234#net_pay"],
            confidence=0.9,
        )
    )
    response = await _assistant(models).answer(AskRequest(employee_id="EMP-100234", question="What is my net pay?"))
    assert any("9,999.99" in w for w in response.warnings)
    assert response.confidence_score < 0.9


@pytest.mark.anyio
async def test_privacy_guard_never_calls_gemini():
    models = _FakeModels(GeminiAnswer(answer="x", answer_found=True, source_ids=[], confidence=1.0))
    response = await _assistant(models).answer(
        AskRequest(employee_id="EMP-100234", question="What is my manager's salary?")
    )
    assert models.calls == []
    assert response.answer_found is False


@pytest.mark.anyio
async def test_gemini_error_falls_back_to_offline_in_auto_mode():
    error = genai_errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    response = await _assistant(_FakeModels(error=error)).answer(
        AskRequest(employee_id="EMP-100234", question="How many vacation days do I have left?")
    )
    assert response.mode == "offline"
    assert response.answer_found is True
    assert any("rate limit" in w for w in response.warnings)


@pytest.mark.anyio
async def test_gemini_error_raises_in_strict_mode():
    error = genai_errors.ServerError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})
    with pytest.raises(AIServiceError) as excinfo:
        await _assistant(_FakeModels(error=error), ai_mode="gemini").answer(
            AskRequest(employee_id="EMP-100234", question="What is my net pay?")
        )
    assert excinfo.value.status_code == 502


@pytest.fixture
def anyio_backend():
    return "asyncio"
