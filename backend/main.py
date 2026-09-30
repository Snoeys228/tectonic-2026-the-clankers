"""FastAPI entrypoint for the Payslip Q&A Assistant.

Run locally from the /backend directory:
    uvicorn main:app --reload --port 8080
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from database import EmployeeNotFoundError, get_repository
from models import (
    EMPLOYEE_ID_PATTERN,
    AskRequest,
    AskResponse,
    EmployeeSummary,
    ErrorResponse,
    HealthResponse,
    PayslipOverview,
)
from services.ai_service import AIServiceError, PayslipAssistant

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("payslip_assistant")

EmployeeIdPath = Annotated[str, Path(pattern=EMPLOYEE_ID_PATTERN, description="Employee id, e.g. EMP-100234")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = get_repository()
    app.state.repository = repository
    app.state.assistant = PayslipAssistant(settings, repository)
    logger.info(
        "Payslip assistant ready: %d employees, %d payslips, ai_mode=%s, gemini=%s",
        len(repository.list_employees()),
        repository.count_payslips(),
        settings.ai_mode,
        app.state.assistant.gemini_configured,
    )
    try:
        yield
    finally:
        await app.state.assistant.aclose()


app = FastAPI(
    title="Payslip Q&A Assistant",
    version="1.0.0",
    description="Retrieval-augmented payslip assistant powered by Gemini, with full source transparency.",
    lifespan=lifespan,
    responses={500: {"model": ErrorResponse}},
)

allow_all_origins = settings.cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=not allow_all_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-ms"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(elapsed_ms)
    if request.url.path.startswith("/api"):
        logger.info("%s %s -> %s in %dms [%s]", request.method, request.url.path, response.status_code,
                    elapsed_ms, request_id)
    return response


def _error(request: Request, status_code: int, error: str, detail=None) -> JSONResponse:
    body = ErrorResponse(error=error, detail=detail, request_id=getattr(request.state, "request_id", None))
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in err.get("loc", []) if part != "body"), "message": err.get("msg")}
        for err in exc.errors()
    ]
    return _error(request, 422, "Invalid request", details)


@app.exception_handler(EmployeeNotFoundError)
async def employee_not_found_handler(request: Request, exc: EmployeeNotFoundError) -> JSONResponse:
    return _error(request, 404, "Employee not found", f"No payslip records exist for employee {exc}.")


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request: Request, exc: AIServiceError) -> JSONResponse:
    return _error(request, exc.status_code, "AI service unavailable", str(exc))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error(request, exc.status_code, str(exc.detail), None)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error [%s]", getattr(request.state, "request_id", "-"))
    return _error(request, 500, "Internal server error", "An unexpected error occurred. Please try again.")


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    repository = request.app.state.repository
    assistant: PayslipAssistant = request.app.state.assistant
    return HealthResponse(
        status="ok",
        ai_mode=settings.ai_mode,
        gemini_configured=assistant.gemini_configured,
        model=settings.gemini_model if assistant.gemini_configured else None,
        employees_loaded=len(repository.list_employees()),
        payslips_loaded=repository.count_payslips(),
    )


@app.get("/api/employees", response_model=list[EmployeeSummary], tags=["payslips"])
async def list_employees(request: Request) -> list[EmployeeSummary]:
    """Demo-only employee picker. In production the employee id comes from the SSO token."""
    repository = request.app.state.repository
    return [
        EmployeeSummary(
            employee_id=employee.employee_id,
            full_name=employee.full_name,
            job_title=employee.job_title,
            department=employee.department,
            employer="Nordvale Logistics NV",
            available_periods=[p.period for p in repository.get_payslips(employee.employee_id)],
        )
        for employee in repository.list_employees()
    ]


@app.get("/api/employees/{employee_id}/payslips", response_model=list[PayslipOverview], tags=["payslips"])
async def list_payslips(employee_id: EmployeeIdPath, request: Request) -> list[PayslipOverview]:
    repository = request.app.state.repository
    employee = repository.get_employee(employee_id.upper())
    return [
        PayslipOverview(
            employee_id=employee.employee_id,
            full_name=employee.full_name,
            document_id=p.document_id,
            period=p.period,
            period_label=p.period_label,
            payment_date=p.payment_date.isoformat(),
            gross_salary=float(p.gross_salary),
            employee_social_security=float(p.employee_social_security),
            withholding_tax=float(p.withholding_tax),
            net_pay=float(p.net_pay),
            meal_vouchers_count=p.meal_vouchers_count,
            remaining_legal_vacation_days=float(p.remaining_legal_vacation_days),
        )
        for p in repository.get_payslips(employee.employee_id)
    ]


@app.get("/api/employees/{employee_id}/payslips/{period}/text", tags=["payslips"])
async def payslip_text(
    employee_id: EmployeeIdPath,
    period: Annotated[str, Path(pattern=r"^\d{4}-\d{2}$", description="Pay period YYYY-MM")],
    request: Request,
) -> dict[str, str]:
    """Full rendered payslip, so the retrieved snippets can be checked against the complete document."""
    repository = request.app.state.repository
    for payslip in repository.get_payslips(employee_id.upper()):
        if payslip.period == period:
            return {"document_id": payslip.document_id, "period": period, "text": payslip.full_text()}
    raise HTTPException(status_code=404, detail=f"No payslip for {employee_id} in {period}")


@app.post(
    "/api/ask",
    response_model=AskResponse,
    tags=["assistant"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 502: {"model": ErrorResponse},
               503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def ask(payload: AskRequest, request: Request) -> AskResponse:
    assistant: PayslipAssistant = request.app.state.assistant
    return await assistant.answer(payload)


if settings.frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
else:
    logger.warning("Frontend directory %s not found; only the API is served", settings.frontend_dir)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"message": "Payslip Q&A Assistant API. See /docs for the OpenAPI documentation."}
