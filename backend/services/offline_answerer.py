"""Deterministic, extractive answerer used when Gemini is not configured or unavailable.

It never invents figures: every sentence is built from the structured payslip record
behind the retrieved snippets, and it cites exactly the snippets it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from database import Payslip
from services.retrieval import RetrievalResult

NOT_FOUND_MESSAGE = (
    "I could not find this information in your payslip documents. "
    "Please rephrase your question or contact your HR/payroll department."
)


@dataclass
class OfflineAnswer:
    answer: str
    answer_found: bool
    source_ids: list[str]
    confidence: float


def _eur(value: Decimal) -> str:
    return f"EUR {value:,.2f}"


def _days(value: Decimal) -> str:
    return f"{value:.1f}"


def _items(payslip_items) -> str:
    return "; ".join(f"{item.label} {item.amount:+,.2f}" for item in payslip_items)


def _sid(payslip: Payslip, section: str) -> str:
    return f"{payslip.document_id}#{section}"


def _describe(section: str, p: Payslip) -> str | None:
    emp = p.employee
    if section == "leave":
        return (
            f"As of {p.period_end:%d/%m/%Y}, you have {_days(p.remaining_legal_vacation_days)} legal vacation days "
            f"remaining for {p.year} (entitlement {_days(emp.legal_vacation_entitlement)}, "
            f"{_days(p.legal_vacation_taken_ytd)} taken year-to-date) and "
            f"{_days(p.remaining_extra_legal_vacation_days)} extra-legal vacation days remaining."
        )
    if section == "meal_vouchers":
        return (
            f"In {p.period_label} you received {p.meal_vouchers_count} meal vouchers (one per day worked, "
            f"{p.days_worked} days) worth {_eur(p.meal_voucher_total_value)} in total; your employee contribution of "
            f"{_eur(p.meal_voucher_employee_contribution)} was deducted from your net pay."
        )
    if section == "tax":
        return (
            f"In {p.period_label} the withholding tax was {_eur(p.withholding_tax)} on a taxable salary of "
            f"{_eur(p.taxable_salary)}, plus a special social security contribution of "
            f"{_eur(p.special_social_security)}."
        )
    if section == "social_security":
        return (
            f"In {p.period_label} your employee social security contribution (RSZ/ONSS, 13.07%) was "
            f"{_eur(p.employee_social_security)} on a gross salary of {_eur(p.gross_salary)}."
        )
    if section == "earnings":
        return f"Your gross salary for {p.period_label} was {_eur(p.gross_salary)} ({_items(p.earnings)})."
    if section == "net_pay":
        return (
            f"Your net pay for {p.period_label} is {_eur(p.net_pay)}, transferred to {emp.iban_masked} "
            f"on {p.payment_date:%d/%m/%Y}."
        )
    if section == "net_adjustments":
        return (
            f"Net allowances and deductions for {p.period_label} total {_eur(p.total_net_adjustments)} "
            f"({_items(p.all_net_adjustments)})."
        )
    if section == "header":
        return (
            f"Your {p.period_label} payslip ({p.document_id}) covers {p.working_days} working days, of which "
            f"{p.days_worked} worked; it was paid on {p.payment_date:%d/%m/%Y}. You are registered as "
            f"{emp.job_title} in {emp.department}."
        )
    return None


def _line_item_changes(previous: Payslip, current: Payslip) -> list[tuple[str, Decimal]]:
    """Changes in individual components, expressed as their effect on net pay."""

    def by_label(items) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for item in items:
            result[item.label] = result.get(item.label, Decimal("0")) + item.amount
        return result

    changes: list[tuple[str, Decimal]] = []
    for group_prev, group_cur in (
        (by_label(previous.earnings), by_label(current.earnings)),
        (by_label(previous.all_net_adjustments), by_label(current.all_net_adjustments)),
    ):
        for label in dict.fromkeys([*group_prev, *group_cur]):
            delta = group_cur.get(label, Decimal("0")) - group_prev.get(label, Decimal("0"))
            if delta:
                changes.append((label, delta))

    for label, prev_value, cur_value in (
        ("Employee social security", previous.employee_social_security, current.employee_social_security),
        ("Withholding tax", previous.withholding_tax, current.withholding_tax),
        ("Special social security contribution", previous.special_social_security, current.special_social_security),
    ):
        delta = -(cur_value - prev_value)
        if delta:
            changes.append((label, delta))

    changes.sort(key=lambda c: abs(c[1]), reverse=True)
    return changes


def _compare(previous: Payslip, current: Payslip) -> tuple[str, list[str]]:
    diff = current.net_pay - previous.net_pay
    if diff == 0:
        direction = "the same as"
    else:
        direction = f"{_eur(abs(diff))} {'lower' if diff < 0 else 'higher'} than"
    lines = [
        f"Your net pay for {current.period_label} is {_eur(current.net_pay)}, {direction} "
        f"{previous.period_label} ({_eur(previous.net_pay)}). Gross salary went from "
        f"{_eur(previous.gross_salary)} to {_eur(current.gross_salary)}. Main differences:"
    ]
    for label, delta in _line_item_changes(previous, current)[:6]:
        lines.append(f"- {label}: {delta:+,.2f} effect on net pay")
    sources = [
        _sid(p, s) for p in (previous, current) for s in ("net_pay", "earnings", "tax", "net_adjustments")
    ]
    return "\n".join(lines), sources


def answer_offline(retrieval: RetrievalResult, payslips: list[Payslip]) -> OfflineAnswer:
    if not retrieval.snippets or not retrieval.keyword_match:
        return OfflineAnswer(NOT_FOUND_MESSAGE, False, [], 0.3)

    by_period = {p.period: p for p in payslips}
    selected = [by_period[period] for period in retrieval.periods if period in by_period]
    available_ids = {s.chunk.source_id for s in retrieval.snippets}
    top_relevance = retrieval.top_relevance
    confidence = round(min(0.9, 0.55 + 0.35 * top_relevance), 2)

    pay_related = {"net_pay", "earnings", "tax", "net_adjustments", "social_security"}
    primary = retrieval.primary_sections()
    if retrieval.is_comparison and len(selected) >= 2 and (set(primary[:2]) & pay_related):
        text, sources = _compare(selected[-2], selected[-1])
        return OfflineAnswer(text, True, [s for s in sources if s in available_ids], confidence)

    sentences: list[str] = []
    sources: list[str] = []
    for section in primary[:2]:
        targets = selected if (len(selected) > 1 and section not in {"leave", "header"}) else selected[-1:]
        for payslip in targets:
            source_id = _sid(payslip, section)
            if source_id not in available_ids:
                continue
            sentence = _describe(section, payslip)
            if sentence:
                sentences.append(sentence)
                sources.append(source_id)

    if not sentences:
        return OfflineAnswer(NOT_FOUND_MESSAGE, False, [], 0.3)
    return OfflineAnswer(" ".join(sentences), True, sources, confidence)
