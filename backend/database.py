"""Mock enterprise payslip store.

The records mimic the structure of a Belgian SD Worx-style payslip: gross earnings,
employee social security (RSZ/ONSS, 13.07%), withholding tax (bedrijfsvoorheffing),
special social security contribution, net allowances/deductions, meal vouchers and
the legal vacation balance.

Only the raw inputs (line items, days worked, leave taken) are stored. All totals are
computed with Decimal arithmetic so every payslip is internally consistent, and each
payslip is rendered into plain-text sections. Those sections are the exact snippets
used as retrieval context for the AI assistant and shown in the transparency box.

All people, companies and account numbers are fictional.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

CURRENCY = "EUR"
CENT = Decimal("0.01")

EMPLOYEE_RSZ_RATE = Decimal("0.1307")
MEAL_VOUCHER_FACE_VALUE = Decimal("8.00")
MEAL_VOUCHER_EMPLOYEE_SHARE = Decimal("1.09")
MEAL_VOUCHER_EMPLOYER_SHARE = MEAL_VOUCHER_FACE_VALUE - MEAL_VOUCHER_EMPLOYEE_SHARE

# Simplified, illustrative withholding tax scale (annualised). Not an official scale.
TAX_BRACKETS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("16320"), Decimal("0.25")),
    (Decimal("28800"), Decimal("0.40")),
    (Decimal("49840"), Decimal("0.45")),
    (Decimal("Infinity"), Decimal("0.50")),
)
PROFESSIONAL_EXPENSES_RATE = Decimal("0.30")
PROFESSIONAL_EXPENSES_CAP = Decimal("5930")
TAX_FREE_ALLOWANCE_REDUCTION = Decimal("2727.50")
MONTHLY_CHILD_REDUCTION = {0: Decimal("0"), 1: Decimal("49.00"), 2: Decimal("131.00"), 3: Decimal("348.00")}

SPECIAL_SSC_THRESHOLD = Decimal("1945.38")
SPECIAL_SSC_RATE = Decimal("0.0112")
SPECIAL_SSC_CAP = Decimal("51.64")

EMPLOYER = {
    "name": "Nordvale Logistics NV",
    "company_number": "BE 0456.789.123",
    "address": "Havenlaan 42, 2000 Antwerpen",
    "payroll_provider": "SD Worx-style payroll export (mock)",
}

SECTION_TITLES: dict[str, str] = {
    "header": "Payslip header",
    "earnings": "Gross earnings",
    "social_security": "Employee social security",
    "tax": "Withholding tax",
    "net_adjustments": "Net allowances and deductions",
    "net_pay": "Net pay",
    "meal_vouchers": "Meal vouchers",
    "leave": "Leave balance",
}


def _d(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _signed(value: Decimal) -> str:
    return f"{value:+,.2f}"


def _days(value: Decimal) -> str:
    return f"{value:.1f}"


def _fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _last_business_day(year: int, month: int) -> date:
    day = calendar.monthrange(year, month)[1]
    candidate = date(year, month, day)
    while candidate.weekday() >= 5:
        day -= 1
        candidate = date(year, month, day)
    return candidate


def hourly_rate(monthly_salary: Decimal, weekly_hours: Decimal) -> Decimal:
    """Belgian convention: monthly salary x 3 / 13 / weekly hours."""
    return monthly_salary * 3 / 13 / weekly_hours


def compute_withholding_tax(taxable_monthly: Decimal, dependent_children: int) -> Decimal:
    annual = taxable_monthly * 12
    professional_expenses = min(annual * PROFESSIONAL_EXPENSES_RATE, PROFESSIONAL_EXPENSES_CAP)
    net_taxable = max(Decimal("0"), annual - professional_expenses)

    tax = Decimal("0")
    lower = Decimal("0")
    for upper, rate in TAX_BRACKETS:
        if net_taxable <= lower:
            break
        tax += (min(net_taxable, upper) - lower) * rate
        lower = upper

    tax = max(Decimal("0"), tax - TAX_FREE_ALLOWANCE_REDUCTION)
    monthly = tax / 12 - MONTHLY_CHILD_REDUCTION.get(min(dependent_children, 3), Decimal("0"))
    return _round(max(Decimal("0"), monthly))


def compute_special_ssc(gross: Decimal) -> Decimal:
    if gross <= SPECIAL_SSC_THRESHOLD:
        return Decimal("0.00")
    return _round(min(SPECIAL_SSC_CAP, (gross - SPECIAL_SSC_THRESHOLD) * SPECIAL_SSC_RATE))


@dataclass(frozen=True)
class LineItem:
    code: str
    label: str
    amount: Decimal
    quantity: str = ""


@dataclass(frozen=True)
class Employee:
    employee_id: str
    first_name: str
    last_name: str
    job_title: str
    department: str
    hire_date: date
    joint_committee: str
    weekly_hours: Decimal
    base_monthly_salary: Decimal
    dependent_children: int
    iban_masked: str
    legal_vacation_entitlement: Decimal
    extra_legal_vacation_entitlement: Decimal
    company_car_benefit: Decimal = Decimal("0.00")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class PayslipChunk:
    source_id: str
    document_id: str
    employee_id: str
    period: str
    period_label: str
    section: str
    section_title: str
    text: str


@dataclass
class Payslip:
    employee: Employee
    year: int
    month: int
    working_days: int
    days_worked: int
    vacation_days: Decimal
    unpaid_leave_days: Decimal
    earnings: list[LineItem]
    net_adjustments: list[LineItem]
    legal_vacation_taken_ytd: Decimal
    extra_legal_vacation_taken_ytd: Decimal
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def period(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def period_label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def document_id(self) -> str:
        return f"PS-{self.year:04d}{self.month:02d}-{self.employee.employee_id.replace('-', '')}"

    @property
    def period_start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def period_end(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    @property
    def payment_date(self) -> date:
        return _last_business_day(self.year, self.month)

    @property
    def gross_salary(self) -> Decimal:
        return _round(sum((item.amount for item in self.earnings), Decimal("0")))

    @property
    def employee_social_security(self) -> Decimal:
        return _round(self.gross_salary * EMPLOYEE_RSZ_RATE)

    @property
    def benefit_in_kind(self) -> Decimal:
        return self.employee.company_car_benefit

    @property
    def taxable_salary(self) -> Decimal:
        return self.gross_salary - self.employee_social_security + self.benefit_in_kind

    @property
    def withholding_tax(self) -> Decimal:
        return compute_withholding_tax(self.taxable_salary, self.employee.dependent_children)

    @property
    def special_social_security(self) -> Decimal:
        return compute_special_ssc(self.gross_salary)

    @property
    def meal_vouchers_count(self) -> int:
        return self.days_worked

    @property
    def meal_voucher_employee_contribution(self) -> Decimal:
        return _round(MEAL_VOUCHER_EMPLOYEE_SHARE * self.meal_vouchers_count)

    @property
    def meal_voucher_total_value(self) -> Decimal:
        return _round(MEAL_VOUCHER_FACE_VALUE * self.meal_vouchers_count)

    @property
    def all_net_adjustments(self) -> list[LineItem]:
        items = list(self.net_adjustments)
        items.append(
            LineItem(
                "4110",
                "Meal vouchers - employee contribution",
                -self.meal_voucher_employee_contribution,
                f"{self.meal_vouchers_count} x {_money(MEAL_VOUCHER_EMPLOYEE_SHARE)}",
            )
        )
        if self.benefit_in_kind:
            items.append(LineItem("4900", "Reversal benefit in kind company car (non-cash)", -self.benefit_in_kind))
        return items

    @property
    def total_net_adjustments(self) -> Decimal:
        return _round(sum((item.amount for item in self.all_net_adjustments), Decimal("0")))

    @property
    def net_pay(self) -> Decimal:
        return _round(
            self.taxable_salary - self.withholding_tax - self.special_social_security + self.total_net_adjustments
        )

    @property
    def remaining_legal_vacation_days(self) -> Decimal:
        return self.employee.legal_vacation_entitlement - self.legal_vacation_taken_ytd

    @property
    def remaining_extra_legal_vacation_days(self) -> Decimal:
        return self.employee.extra_legal_vacation_entitlement - self.extra_legal_vacation_taken_ytd

    def render_sections(self) -> None:
        emp = self.employee
        lines_earnings = [
            f"{item.code}  {item.label:<52} {item.quantity:>16} {_money(item.amount):>12}" for item in self.earnings
        ]
        lines_net = [
            f"{item.code}  {item.label:<52} {item.quantity:>16} {_signed(item.amount):>12}"
            for item in self.all_net_adjustments
        ]
        bik_line = (
            f"3050  Benefit in kind company car (taxable, not subject to RSZ) = EUR {_signed(self.benefit_in_kind)}"
            if self.benefit_in_kind
            else "3050  Benefit in kind: none"
        )

        self.sections = {
            "header": "\n".join(
                [
                    "PAYSLIP - SD WORX-STYLE FORMAT (MOCK DATA)",
                    f"Document no.: {self.document_id}",
                    f"Employer: {EMPLOYER['name']} | Company no. {EMPLOYER['company_number']} | {EMPLOYER['address']}",
                    f"Employee: {emp.full_name} ({emp.employee_id}) | {emp.job_title} | {emp.department}",
                    f"Joint committee (PC): {emp.joint_committee} | Hire date: {_fmt_date(emp.hire_date)}"
                    f" | Weekly schedule: {emp.weekly_hours}h",
                    f"Pay period: {_fmt_date(self.period_start)} - {_fmt_date(self.period_end)}"
                    f" | Payment date: {_fmt_date(self.payment_date)}",
                    f"Working days in period: {self.working_days} | Days worked: {self.days_worked}"
                    f" | Vacation days: {_days(self.vacation_days)} | Unpaid leave days: {_days(self.unpaid_leave_days)}",
                    f"Dependent children (tax): {emp.dependent_children} | Bank account: {emp.iban_masked}",
                ]
            ),
            "earnings": "\n".join(
                [
                    f"GROSS EARNINGS - {self.period_label}",
                    f"Code  {'Description':<52} {'Quantity':>16} {'Amount EUR':>12}",
                    *lines_earnings,
                    f"TOTAL GROSS SALARY{'':>56}{_money(self.gross_salary):>13}",
                ]
            ),
            "social_security": "\n".join(
                [
                    f"EMPLOYEE SOCIAL SECURITY (RSZ/ONSS) - {self.period_label}",
                    f"Gross salary subject to social security: EUR {_money(self.gross_salary)}",
                    f"2010  Employee social security contribution 13.07% x {_money(self.gross_salary)}"
                    f" = EUR {_signed(-self.employee_social_security)}",
                    bik_line,
                    f"TAXABLE SALARY (gross - social security + benefits in kind): EUR {_money(self.taxable_salary)}",
                ]
            ),
            "tax": "\n".join(
                [
                    f"WITHHOLDING TAX (BEDRIJFSVOORHEFFING / PRECOMPTE PROFESSIONNEL) - {self.period_label}",
                    f"Taxable salary: EUR {_money(self.taxable_salary)}"
                    f" | Dependent children taken into account: {emp.dependent_children}",
                    f"3010  Withholding tax on taxable salary = EUR {_signed(-self.withholding_tax)}",
                    f"3020  Special social security contribution (BBSZ/CSSS) = EUR {_signed(-self.special_social_security)}",
                    f"TOTAL TAX WITHHELD: EUR {_signed(-(self.withholding_tax + self.special_social_security))}",
                ]
            ),
            "net_adjustments": "\n".join(
                [
                    f"NET ALLOWANCES AND DEDUCTIONS - {self.period_label}",
                    f"Code  {'Description':<52} {'Quantity':>16} {'Amount EUR':>12}",
                    *lines_net,
                    f"TOTAL NET ALLOWANCES AND DEDUCTIONS: EUR {_signed(self.total_net_adjustments)}",
                ]
            ),
            "net_pay": "\n".join(
                [
                    f"NET PAY CALCULATION - {self.period_label}",
                    f"Gross salary:                          EUR {_money(self.gross_salary)}",
                    f"Employee social security (13.07%):     EUR {_signed(-self.employee_social_security)}",
                    f"Benefit in kind (taxable only):        EUR {_signed(self.benefit_in_kind)}",
                    f"Taxable salary:                        EUR {_money(self.taxable_salary)}",
                    f"Withholding tax:                       EUR {_signed(-self.withholding_tax)}",
                    f"Special social security contribution:  EUR {_signed(-self.special_social_security)}",
                    f"Net allowances and deductions:         EUR {_signed(self.total_net_adjustments)}",
                    f"NET PAY: EUR {_money(self.net_pay)} transferred to {emp.iban_masked}"
                    f" on {_fmt_date(self.payment_date)}",
                ]
            ),
            "meal_vouchers": "\n".join(
                [
                    f"MEAL VOUCHERS (ELECTRONIC CARD) - {self.period_label}",
                    f"Vouchers granted: {self.meal_vouchers_count} (1 voucher per day actually worked;"
                    f" {self.days_worked} days worked)",
                    f"Face value per voucher: EUR {_money(MEAL_VOUCHER_FACE_VALUE)}"
                    f" (employer share EUR {_money(MEAL_VOUCHER_EMPLOYER_SHARE)}"
                    f" / employee share EUR {_money(MEAL_VOUCHER_EMPLOYEE_SHARE)})",
                    f"Total value loaded on meal voucher card: EUR {_money(self.meal_voucher_total_value)}",
                    f"Employee contribution deducted from net pay: EUR {_money(self.meal_voucher_employee_contribution)}",
                ]
            ),
            "leave": "\n".join(
                [
                    f"LEAVE BALANCE {self.year} (status on {_fmt_date(self.period_end)})",
                    f"Legal vacation days: entitlement {_days(emp.legal_vacation_entitlement)}"
                    f" | taken this period {_days(self.vacation_days)}"
                    f" | taken year-to-date {_days(self.legal_vacation_taken_ytd)}"
                    f" | REMAINING {_days(self.remaining_legal_vacation_days)}",
                    f"Extra-legal vacation days: entitlement {_days(emp.extra_legal_vacation_entitlement)}"
                    f" | taken year-to-date {_days(self.extra_legal_vacation_taken_ytd)}"
                    f" | remaining {_days(self.remaining_extra_legal_vacation_days)}",
                    f"Unpaid leave this period: {_days(self.unpaid_leave_days)} day(s)",
                    f"Legal vacation entitlement for {self.year} is based on days worked in reference year {self.year - 1}.",
                ]
            ),
        }

    def chunks(self) -> list[PayslipChunk]:
        if not self.sections:
            self.render_sections()
        return [
            PayslipChunk(
                source_id=f"{self.document_id}#{key}",
                document_id=self.document_id,
                employee_id=self.employee.employee_id,
                period=self.period,
                period_label=self.period_label,
                section=key,
                section_title=SECTION_TITLES[key],
                text=text,
            )
            for key, text in self.sections.items()
        ]

    def full_text(self) -> str:
        if not self.sections:
            self.render_sections()
        return "\n\n".join(self.sections.values())


def _base(emp_salary: str) -> LineItem:
    return LineItem("1010", "Base monthly salary", _d(emp_salary))


def _overtime(employee: Employee, hours: int, premium_pct: int) -> LineItem:
    rate = hourly_rate(employee.base_monthly_salary, employee.weekly_hours) * (1 + _d(premium_pct) / 100)
    return LineItem(
        "1210",
        f"Overtime {100 + premium_pct}%",
        _round(rate * hours),
        f"{hours}h x {_money(_round(rate))}",
    )


def _unpaid_leave(employee: Employee, days: int) -> LineItem:
    hours_per_day = employee.weekly_hours / 5
    rate = hourly_rate(employee.base_monthly_salary, employee.weekly_hours)
    return LineItem(
        "1510",
        "Unpaid leave deduction",
        -_round(rate * hours_per_day * days),
        f"{days}d x {hours_per_day}h",
    )


def _build_records() -> dict[str, tuple[Employee, list[Payslip]]]:
    sophie = Employee(
        employee_id="EMP-100234",
        first_name="Sophie",
        last_name="Janssens",
        job_title="Senior Data Analyst",
        department="Finance & Analytics",
        hire_date=date(2019, 3, 1),
        joint_committee="200",
        weekly_hours=_d(38),
        base_monthly_salary=_d("4250.00"),
        dependent_children=0,
        iban_masked="BE71 **** **** 4410",
        legal_vacation_entitlement=_d(20),
        extra_legal_vacation_entitlement=_d(2),
    )
    lucas = Employee(
        employee_id="EMP-100587",
        first_name="Lucas",
        last_name="Peeters",
        job_title="Warehouse Team Lead",
        department="Operations - Hub Antwerp",
        hire_date=date(2016, 9, 12),
        joint_committee="226",
        weekly_hours=_d(38),
        base_monthly_salary=_d("3180.00"),
        dependent_children=2,
        iban_masked="BE38 **** **** 9021",
        legal_vacation_entitlement=_d(20),
        extra_legal_vacation_entitlement=_d(0),
    )
    amira = Employee(
        employee_id="EMP-100912",
        first_name="Amira",
        last_name="El Idrissi",
        job_title="Software Engineer",
        department="Digital Platforms",
        hire_date=date(2022, 1, 17),
        joint_committee="200",
        weekly_hours=_d(38),
        base_monthly_salary=_d("5120.00"),
        dependent_children=1,
        iban_masked="BE12 **** **** 7733",
        legal_vacation_entitlement=_d(20),
        extra_legal_vacation_entitlement=_d(6),
        company_car_benefit=_d("142.50"),
    )

    telework = LineItem("4010", "Teleworking allowance (tax-free)", _d("151.70"))
    public_transport = LineItem("4020", "Public transport commuting reimbursement", _d("62.40"))

    def bike_commute(days: int) -> LineItem:
        return LineItem("4030", "Bicycle commuting allowance", _round(_d("4.20") * days), f"{days}d x 4.20")

    records: dict[str, tuple[Employee, list[Payslip]]] = {
        sophie.employee_id: (
            sophie,
            [
                Payslip(
                    employee=sophie, year=2026, month=7, working_days=22, days_worked=19,
                    vacation_days=_d(3), unpaid_leave_days=_d(0),
                    earnings=[_base("4250.00")],
                    net_adjustments=[
                        telework,
                        public_transport,
                        LineItem("4210", "Hospitalisation insurance premium", _d("-18.45")),
                    ],
                    legal_vacation_taken_ytd=_d(11), extra_legal_vacation_taken_ytd=_d(0),
                ),
                Payslip(
                    employee=sophie, year=2026, month=8, working_days=21, days_worked=16,
                    vacation_days=_d(5), unpaid_leave_days=_d(0),
                    earnings=[_base("4250.00"), _overtime(sophie, 5, 50)],
                    net_adjustments=[
                        telework,
                        public_transport,
                        LineItem("4210", "Hospitalisation insurance premium", _d("-18.45")),
                    ],
                    legal_vacation_taken_ytd=_d(16), extra_legal_vacation_taken_ytd=_d(0),
                ),
                Payslip(
                    employee=sophie, year=2026, month=9, working_days=22, days_worked=21,
                    vacation_days=_d(0), unpaid_leave_days=_d(1),
                    earnings=[
                        _base("4250.00"),
                        _unpaid_leave(sophie, 1),
                        LineItem("1720", "Bike lease - gross salary sacrifice (new contract)", _d("-52.30")),
                    ],
                    net_adjustments=[
                        telework,
                        public_transport,
                        LineItem("4210", "Hospitalisation insurance premium", _d("-18.45")),
                    ],
                    legal_vacation_taken_ytd=_d(16), extra_legal_vacation_taken_ytd=_d(0),
                ),
            ],
        ),
        lucas.employee_id: (
            lucas,
            [
                Payslip(
                    employee=lucas, year=2026, month=7, working_days=22, days_worked=12,
                    vacation_days=_d(10), unpaid_leave_days=_d(0),
                    earnings=[_base("3180.00"), LineItem("1310", "Night shift premium", _d("95.40"), "4 shifts")],
                    net_adjustments=[bike_commute(12)],
                    legal_vacation_taken_ytd=_d(14), extra_legal_vacation_taken_ytd=_d(0),
                ),
                Payslip(
                    employee=lucas, year=2026, month=8, working_days=21, days_worked=21,
                    vacation_days=_d(0), unpaid_leave_days=_d(0),
                    earnings=[
                        _base("3180.00"),
                        LineItem("1310", "Night shift premium", _d("286.20"), "12 shifts"),
                        _overtime(lucas, 8, 50),
                    ],
                    net_adjustments=[bike_commute(21)],
                    legal_vacation_taken_ytd=_d(14), extra_legal_vacation_taken_ytd=_d(0),
                ),
                Payslip(
                    employee=lucas, year=2026, month=9, working_days=22, days_worked=20,
                    vacation_days=_d(2), unpaid_leave_days=_d(0),
                    earnings=[_base("3180.00"), LineItem("1310", "Night shift premium", _d("238.50"), "10 shifts")],
                    net_adjustments=[bike_commute(20)],
                    legal_vacation_taken_ytd=_d(16), extra_legal_vacation_taken_ytd=_d(0),
                ),
            ],
        ),
        amira.employee_id: (
            amira,
            [
                Payslip(
                    employee=amira, year=2026, month=7, working_days=22, days_worked=17,
                    vacation_days=_d(5), unpaid_leave_days=_d(0),
                    earnings=[_base("5120.00")],
                    net_adjustments=[
                        telework,
                        LineItem("4210", "Hospitalisation insurance premium (family)", _d("-24.10")),
                    ],
                    legal_vacation_taken_ytd=_d(11), extra_legal_vacation_taken_ytd=_d(2),
                ),
                Payslip(
                    employee=amira, year=2026, month=8, working_days=21, days_worked=21,
                    vacation_days=_d(0), unpaid_leave_days=_d(0),
                    earnings=[_base("5120.00")],
                    net_adjustments=[
                        telework,
                        LineItem("4210", "Hospitalisation insurance premium (family)", _d("-24.10")),
                    ],
                    legal_vacation_taken_ytd=_d(11), extra_legal_vacation_taken_ytd=_d(2),
                ),
                Payslip(
                    employee=amira, year=2026, month=9, working_days=22, days_worked=21,
                    vacation_days=_d(1), unpaid_leave_days=_d(0),
                    earnings=[_base("5120.00"), LineItem("1810", "Employee referral bonus (taxable)", _d("500.00"))],
                    net_adjustments=[
                        telework,
                        LineItem("4210", "Hospitalisation insurance premium (family)", _d("-24.10")),
                    ],
                    legal_vacation_taken_ytd=_d(12), extra_legal_vacation_taken_ytd=_d(2),
                ),
            ],
        ),
    }

    for _, payslips in records.values():
        payslips.sort(key=lambda p: p.period)
        for payslip in payslips:
            payslip.render_sections()
    return records


class EmployeeNotFoundError(LookupError):
    pass


class PayslipRepository:
    """Read-only access layer. Swap this for a real payroll API/database in production."""

    def __init__(self) -> None:
        self._records = _build_records()

    def list_employees(self) -> list[Employee]:
        return [employee for employee, _ in self._records.values()]

    def get_employee(self, employee_id: str) -> Employee:
        try:
            return self._records[employee_id][0]
        except KeyError as exc:
            raise EmployeeNotFoundError(employee_id) from exc

    def get_payslips(self, employee_id: str) -> list[Payslip]:
        try:
            return list(self._records[employee_id][1])
        except KeyError as exc:
            raise EmployeeNotFoundError(employee_id) from exc

    def get_latest_payslip(self, employee_id: str) -> Payslip:
        return self.get_payslips(employee_id)[-1]

    def count_payslips(self) -> int:
        return sum(len(payslips) for _, payslips in self._records.values())


@lru_cache(maxsize=1)
def get_repository() -> PayslipRepository:
    return PayslipRepository()
