"""Lightweight, deterministic retriever over payslip sections.

Payslips are small, highly structured documents, so a transparent keyword/lexical
retriever is more predictable (and auditable) than embeddings: judges and employees
can see exactly why a snippet was selected. The retriever:

1. Resolves which pay periods the question refers to (explicit months, "this month",
   "last month", comparisons, year-to-date).
2. Scores every section of those payslips against the question.
3. Returns the best matching sections as ranked snippets.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field

from database import Payslip, PayslipChunk

MAX_SNIPPETS = 10
MAX_SECTIONS_PER_PERIOD = 4
MIN_SECTION_SCORE = 0.9
RELATIVE_THRESHOLD = 0.4
SCORE_NORMALISER = 3.0

STOPWORDS = {
    "a", "about", "am", "an", "and", "are", "as", "at", "be", "been", "by", "can", "could", "did", "do",
    "does", "for", "from", "get", "got", "had", "has", "have", "how", "i", "if", "in", "is", "it", "its",
    "me", "much", "my", "of", "on", "or", "so", "than", "that", "the", "their", "there", "this", "to",
    "was", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your", "month",
    "months", "payslip", "payslips", "please", "tell", "show", "explain", "many",
}

SECTION_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "header": [
        ("employer", 1.5), ("company", 1.0), ("job", 1.0), ("title", 0.8), ("position", 1.0),
        ("department", 1.5), ("hire", 1.5), ("hired", 1.5), ("joined", 1.0), ("iban", 2.0),
        ("bank account", 2.0), ("account", 1.0), ("payment date", 2.0), ("paid on", 1.5),
        ("committee", 2.0), ("schedule", 1.5), ("hours per week", 1.5), ("weekly hours", 1.5),
        ("document", 1.0), ("working days", 1.5), ("days worked", 1.5), ("worked", 0.8),
    ],
    "earnings": [
        ("gross", 2.0), ("salary", 1.2), ("base", 1.0), ("overtime", 2.0), ("bonus", 2.0),
        ("premium", 1.2), ("shift", 1.5), ("night", 1.0), ("earnings", 2.0), ("earned", 1.5),
        ("unpaid", 1.5), ("bike lease", 2.0), ("lease", 1.5), ("sacrifice", 1.5), ("referral", 2.0),
        ("raise", 1.0), ("wage", 1.2), ("brut", 1.5),
    ],
    "social_security": [
        ("social security", 2.5), ("rsz", 3.0), ("onss", 3.0), ("social contribution", 2.0),
        ("13.07", 3.0), ("contribution", 1.0), ("contributions", 1.0),
    ],
    "tax": [
        ("tax", 2.5), ("taxes", 2.5), ("withholding", 3.0), ("bedrijfsvoorheffing", 3.0),
        ("precompte", 3.0), ("bbsz", 3.0), ("csss", 3.0), ("special social", 2.0), ("dependent", 1.0),
        ("children", 1.0), ("taxable", 1.5), ("withheld", 2.0),
    ],
    "net_adjustments": [
        ("allowance", 2.0), ("allowances", 2.0), ("reimbursement", 2.0), ("reimbursed", 2.0),
        ("commuting", 2.0), ("commute", 2.0), ("telework", 2.5), ("teleworking", 2.5), ("remote", 1.5),
        ("home office", 2.0), ("hospitalisation", 2.5), ("hospitalization", 2.5), ("insurance", 2.0),
        ("deduction", 1.5), ("deductions", 1.5), ("deducted", 1.2), ("bicycle", 2.0), ("cycling", 1.5),
        ("company car", 2.5), ("benefit in kind", 2.5), ("bik", 2.5), ("transport", 1.5), ("train", 1.5),
    ],
    "net_pay": [
        ("net", 2.5), ("take home", 2.5), ("take-home", 2.5), ("paid", 1.0), ("transferred", 1.5),
        ("receive", 1.2), ("received", 1.2), ("pay", 0.6), ("lower", 1.0), ("higher", 1.0),
        ("less", 0.8), ("more", 0.6), ("bank", 0.8),
    ],
    "meal_vouchers": [
        ("meal", 3.0), ("voucher", 3.0), ("vouchers", 3.0), ("lunch", 2.5), ("maaltijd", 3.0),
        ("cheque", 2.0), ("cheques", 2.0), ("food", 1.5), ("restaurant", 1.5),
    ],
    "leave": [
        ("vacation", 3.0), ("holiday", 2.5), ("holidays", 2.5), ("leave", 2.0), ("days off", 2.5),
        ("day off", 2.5), ("pto", 3.0), ("time off", 2.5), ("vakantie", 3.0), ("verlof", 3.0),
        ("conge", 3.0), ("remaining", 1.0), ("left", 0.8), ("balance", 1.0),
    ],
}

COMPARISON_TERMS = {
    "compare", "compared", "comparison", "versus", "vs", "difference", "differ", "different", "change",
    "changed", "changes", "lower", "higher", "less", "increase", "increased", "decrease",
    "decreased", "drop", "dropped", "jump", "jumped", "fell", "rise", "rose",
}
PAY_SECTIONS = {"net_pay", "earnings", "tax", "net_adjustments", "social_security", "header"}
COMPARISON_BOOSTS = {
    "net_pay": 2.5, "earnings": 2.0, "tax": 1.2, "net_adjustments": 1.0, "social_security": 0.8, "header": 0.6,
}
ALL_PERIOD_PHRASES = (
    "year to date", "year-to-date", "ytd", "so far this year", "every month", "each month", "all months",
    "all my payslips", "last three months", "last 3 months", "past three months", "past 3 months",
    "this quarter", "trend", "over time",
)
LATEST_PHRASES = ("this month", "current month", "latest", "most recent", "this payslip", "current payslip")
PREVIOUS_PHRASES = ("last month", "previous month", "prior month", "month before", "previous payslip")

_MONTHS: dict[str, int] = {}
for _index in range(1, 13):
    _MONTHS[calendar.month_name[_index].lower()] = _index
    _MONTHS[calendar.month_abbr[_index].lower()] = _index
_MONTHS.update({"sept": 9, "juli": 7, "augustus": 8, "september": 9, "juillet": 7, "aout": 8, "septembre": 9})
_MONTH_WORDS = sorted((m for m in _MONTHS if m != "may"), key=len, reverse=True)
_MONTH_RE = re.compile(r"\b(" + "|".join(_MONTH_WORDS) + r")\b(?:\s+(\d{4}))?")
_MAY_RE = re.compile(r"\b(?:in|of|for|during)\s+may\b(?:\s+(\d{4}))?|\bmay\s+(\d{4})\b")
_ISO_PERIOD_RE = re.compile(r"\b(\d{4})-(\d{1,2})\b|\b(\d{1,2})/(\d{4})\b")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]|[a-z0-9]")


@dataclass
class RankedChunk:
    chunk: PayslipChunk
    relevance: float


@dataclass
class RetrievalResult:
    snippets: list[RankedChunk]
    periods: list[str]
    matched_sections: list[str]
    is_comparison: bool
    missing_periods: list[str] = field(default_factory=list)
    keyword_match: bool = True
    section_scores: dict[str, float] = field(default_factory=dict)

    def primary_sections(self, ratio: float = 0.5, minimum: float = 1.0) -> list[str]:
        """Sections the question is clearly about, strongest first."""
        if not self.section_scores:
            return []
        top = max(self.section_scores.values())
        return [
            s for s in self.matched_sections
            if self.section_scores.get(s, 0.0) >= max(minimum, top * ratio)
        ]

    @property
    def top_relevance(self) -> float:
        return max((s.relevance for s in self.snippets), default=0.0)


def normalise(text: str) -> str:
    text = text.lower()
    replacements = {"é": "e", "è": "e", "ê": "e", "à": "a", "â": "a", "û": "u", "ô": "o", "ç": "c", "’": "'"}
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalise(text))


def _keyword_hit(keyword: str, tokens: list[str], joined: str) -> bool:
    if " " in keyword or "-" in keyword or "." in keyword:
        return f" {keyword} " in f" {joined} "
    for token in tokens:
        if token == keyword or (len(keyword) >= 5 and token.startswith(keyword)):
            return True
    return False


def keyword_scores(question: str) -> dict[str, float]:
    tokens = tokenize(question)
    joined = " ".join(tokens)
    scores: dict[str, float] = {}
    for section, keywords in SECTION_KEYWORDS.items():
        score = sum(weight for keyword, weight in keywords if _keyword_hit(keyword, tokens, joined))
        if score:
            scores[section] = score
    return scores


def is_comparison_question(question: str) -> bool:
    text = normalise(question)
    tokens = set(tokenize(question))
    mentions_two = any(p in text for p in LATEST_PHRASES) and any(p in text for p in PREVIOUS_PHRASES)
    return mentions_two or bool(tokens & COMPARISON_TERMS)


def _label(period: str) -> str:
    year, month = period.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


def resolve_periods(question: str, payslips: list[Payslip]) -> tuple[list[str], list[str], bool]:
    """Return (periods to use, requested-but-missing periods, is_comparison)."""
    available = [p.period for p in payslips]
    if not available:
        return [], [], False
    latest_year = int(available[-1][:4])
    text = normalise(question)
    comparison = is_comparison_question(question)

    requested: list[str] = []
    for match in _MONTH_RE.finditer(text):
        year = int(match.group(2)) if match.group(2) else latest_year
        requested.append(f"{year:04d}-{_MONTHS[match.group(1)]:02d}")
    for match in _MAY_RE.finditer(text):
        year_str = match.group(1) or match.group(2)
        requested.append(f"{int(year_str) if year_str else latest_year:04d}-05")
    for match in _ISO_PERIOD_RE.finditer(text):
        year, month = (match.group(1), match.group(2)) if match.group(1) else (match.group(4), match.group(3))
        if 1 <= int(month) <= 12:
            requested.append(f"{int(year):04d}-{int(month):02d}")

    if any(p in text for p in LATEST_PHRASES):
        requested.append(available[-1])
    if any(p in text for p in PREVIOUS_PHRASES) and len(available) > 1:
        requested.append(available[-2])
        if comparison:
            # "compared to last month" implicitly means: latest payslip vs the previous one.
            requested.append(available[-1])

    requested = list(dict.fromkeys(requested))
    missing = [p for p in requested if p not in available]
    found = [p for p in requested if p in available]

    if any(p in text for p in ALL_PERIOD_PHRASES):
        return available, missing, comparison

    if requested and not found:
        return [], missing, comparison

    if not found:
        found = [available[-1]]

    if comparison and len(found) == 1:
        index = available.index(found[0])
        if index > 0:
            found = [available[index - 1], found[0]]
        elif len(available) > 1:
            found = [found[0], available[1]]

    return sorted(found), missing, comparison


def retrieve(question: str, payslips: list[Payslip]) -> RetrievalResult:
    periods, missing, comparison = resolve_periods(question, payslips)
    if not periods:
        return RetrievalResult([], [], [], comparison, missing, keyword_match=False)

    section_scores = keyword_scores(question)
    if comparison and not (set(section_scores) - PAY_SECTIONS):
        for section, boost in COMPARISON_BOOSTS.items():
            section_scores[section] = section_scores.get(section, 0.0) + boost

    content_tokens = {t for t in tokenize(question) if t not in STOPWORDS and len(t) > 2}
    by_period = {p.period: p for p in payslips}

    ranked: list[RankedChunk] = []
    keyword_match = bool(section_scores)
    for period in periods:
        period_ranked: list[RankedChunk] = []
        for chunk in by_period[period].chunks():
            chunk_tokens = set(tokenize(chunk.text))
            lexical = 0.3 * len(content_tokens & chunk_tokens)
            score = section_scores.get(chunk.section, 0.0) + lexical
            if score > 0:
                period_ranked.append(RankedChunk(chunk, min(1.0, round(score / SCORE_NORMALISER, 3))))
        period_ranked.sort(key=lambda r: r.relevance, reverse=True)
        if period_ranked:
            best = period_ranked[0].relevance
            cutoff = max(MIN_SECTION_SCORE / SCORE_NORMALISER, best * RELATIVE_THRESHOLD)
            period_ranked = [r for r in period_ranked if r.relevance >= cutoff][:MAX_SECTIONS_PER_PERIOD]
        ranked.extend(period_ranked)

    if not ranked:
        # No section matched: fall back to the full latest requested payslip with a low relevance,
        # so the model can still look for the answer (or state it is not there).
        keyword_match = False
        ranked = [RankedChunk(chunk, 0.15) for chunk in by_period[periods[-1]].chunks()]

    ranked.sort(key=lambda r: (r.chunk.period, -r.relevance))
    if len(ranked) > MAX_SNIPPETS:
        keep = sorted(ranked, key=lambda r: r.relevance, reverse=True)[:MAX_SNIPPETS]
        ranked = sorted(keep, key=lambda r: (r.chunk.period, -r.relevance))

    matched_sections = sorted({r.chunk.section for r in ranked}, key=lambda s: -section_scores.get(s, 0.0))
    return RetrievalResult(ranked, periods, matched_sections, comparison, missing, keyword_match, section_scores)


def period_label(period: str) -> str:
    return _label(period)
