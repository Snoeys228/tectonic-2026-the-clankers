"""Pydantic request/response models for the Payslip Q&A API."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMPLOYEE_ID_PATTERN = r"^EMP-\d{6}$"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    employee_id: str = Field(
        ...,
        description="Identifier of the authenticated employee, e.g. EMP-100234.",
        examples=["EMP-100234"],
    )
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question about the employee's own payslips.",
        examples=["Why is my net pay lower this month compared to last month?"],
    )

    @field_validator("employee_id")
    @classmethod
    def normalise_employee_id(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(EMPLOYEE_ID_PATTERN, value):
            raise ValueError("employee_id must look like EMP-123456")
        return value

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = _CONTROL_CHARS.sub("", value)
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) < 3:
            raise ValueError("question must contain at least 3 visible characters")
        return value


class SourceSnippet(BaseModel):
    source_id: str = Field(..., description="Stable reference of the snippet, e.g. PS-202609-EMP100234#net_pay")
    document_id: str = Field(..., description="Payslip document number.")
    period: str = Field(..., description="Pay period in YYYY-MM format.")
    period_label: str = Field(..., description="Human readable pay period, e.g. September 2026.")
    section: str = Field(..., description="Machine readable payslip section key.")
    section_title: str = Field(..., description="Human readable section title.")
    text: str = Field(..., description="Exact payslip text passed to the model as context.")
    relevance: float = Field(..., ge=0.0, le=1.0, description="Retrieval relevance score (0-1).")
    cited: bool = Field(..., description="True if the answer explicitly relied on this snippet.")


class AskResponse(BaseModel):
    answer_summary: str = Field(..., description="Answer grounded in the retrieved payslip text.")
    answer_found: bool = Field(..., description="False when the payslip text does not contain the answer.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Combined retrieval + model confidence (0-1).")
    source_snippets: list[SourceSnippet] = Field(default_factory=list)
    employee_id: str
    periods_considered: list[str] = Field(default_factory=list)
    mode: Literal["gemini", "offline"] = Field(..., description="Which engine produced the answer.")
    model: str | None = Field(None, description="Gemini model name when mode is 'gemini'.")
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = Field(..., ge=0)


class EmployeeSummary(BaseModel):
    employee_id: str
    full_name: str
    job_title: str
    department: str
    employer: str
    available_periods: list[str]


class PayslipOverview(BaseModel):
    employee_id: str
    full_name: str
    document_id: str
    period: str
    period_label: str
    payment_date: str
    gross_salary: float
    employee_social_security: float
    withholding_tax: float
    net_pay: float
    meal_vouchers_count: int
    remaining_legal_vacation_days: float
    currency: str = "EUR"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    ai_mode: str
    gemini_configured: bool
    model: str | None
    employees_loaded: int
    payslips_loaded: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | list | dict | None = None
    request_id: str | None = None
