"use strict";

(() => {
  const API_BASE = window.PAYSLIP_API_BASE || "";
  const REQUEST_TIMEOUT_MS = 60000;

  const SUGGESTIONS = [
    "Why is my net pay lower this month compared to last month?",
    "How many vacation days do I have left?",
    "How many meal vouchers did I get this month?",
    "How much withholding tax did I pay in September?",
    "What are my social security contributions?",
    "What was my gross salary in August?",
    "Which allowances and deductions are on my payslip?",
    "What is my manager's salary?",
  ];

  const SECTION_ICONS = {
    header: "M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z",
    earnings: "M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941",
    social_security: "M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z",
    tax: "M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0 0 12 9.75c-2.551 0-5.056.2-7.5.582V21M3 21h18M12 6.75h.008v.008H12V6.75Z",
    net_adjustments: "M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75",
    net_pay: "M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z",
    meal_vouchers: "M12 8.25v-1.5m0 1.5c-1.355 0-2.697.056-4.024.166C6.845 8.51 6 9.473 6 10.608v2.513m6-4.871c1.355 0 2.697.056 4.024.166C17.155 8.51 18 9.473 18 10.608v2.513M15 8.25v-1.5m-6 1.5v-1.5m12 9.75-1.5.75a3.354 3.354 0 0 1-3 0 3.354 3.354 0 0 0-3 0 3.354 3.354 0 0 1-3 0 3.354 3.354 0 0 0-3 0 3.354 3.354 0 0 1-3 0L3 16.5m15-3.379a48.474 48.474 0 0 0-6-.371c-2.032 0-4.034.126-6 .371m12 0c.39.049.777.102 1.163.16 1.07.16 1.837 1.094 1.837 2.175v5.169c0 .621-.504 1.125-1.125 1.125H4.125A1.125 1.125 0 0 1 3 20.625v-5.17c0-1.08.768-2.014 1.837-2.174A47.78 47.78 0 0 1 6 13.12",
    leave: "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5",
  };

  const AMOUNT_RE = /(?<![\d.,])-?\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?!\d)|(?<![\d.,])-?\d+\.\d{2}(?!\d)/g;

  const el = {
    employeeSelect: document.getElementById("employee-select"),
    engineBadge: document.getElementById("engine-badge"),
    overviewPeriod: document.getElementById("overview-period"),
    overviewNet: document.getElementById("overview-net"),
    overviewEmployee: document.getElementById("overview-employee"),
    overviewStats: document.getElementById("overview-stats"),
    payslipList: document.getElementById("payslip-list"),
    conversation: document.getElementById("conversation"),
    emptyState: document.getElementById("empty-state"),
    suggestions: document.getElementById("suggestions"),
    quickSuggestions: document.getElementById("quick-suggestions"),
    form: document.getElementById("ask-form"),
    question: document.getElementById("question"),
    askButton: document.getElementById("ask-button"),
    askButtonLabel: document.getElementById("ask-button-label"),
    charCount: document.getElementById("char-count"),
    modal: document.getElementById("payslip-modal"),
    modalTitle: document.getElementById("modal-title"),
    modalSubtitle: document.getElementById("modal-subtitle"),
    modalBody: document.getElementById("modal-body"),
    modalClose: document.getElementById("modal-close"),
  };

  const state = {
    employees: [],
    employeeId: null,
    payslips: [],
    busy: false,
  };

  const eur = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });

  class ApiError extends Error {
    constructor(message, { status = 0, detail = null, requestId = null } = {}) {
      super(message);
      this.status = status;
      this.detail = detail;
      this.requestId = requestId;
    }
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name === "AbortError") {
        throw new ApiError("The request timed out. Please try again.");
      }
      throw new ApiError("Cannot reach the server. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }

    let payload = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      const requestId = (payload && payload.request_id) || response.headers.get("X-Request-ID");
      throw new ApiError((payload && payload.error) || `Request failed (HTTP ${response.status})`, {
        status: response.status,
        detail: payload ? payload.detail : null,
        requestId,
      });
    }
    return payload;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normaliseAmount(raw) {
    const value = Math.abs(parseFloat(String(raw).replace(/,/g, "")));
    return Number.isFinite(value) ? value.toFixed(2) : null;
  }

  function amountsIn(text) {
    const result = new Set();
    for (const match of String(text).matchAll(AMOUNT_RE)) {
      const normalised = normaliseAmount(match[0]);
      if (normalised) result.add(normalised);
    }
    return result;
  }

  function highlightSnippet(text, amounts) {
    const escaped = escapeHtml(text);
    if (!amounts.size) return escaped;
    return escaped.replace(AMOUNT_RE, (match) => {
      const normalised = normaliseAmount(match);
      return normalised && amounts.has(normalised) ? `<mark>${match}</mark>` : match;
    });
  }

  function renderAnswerText(text) {
    const lines = String(text).split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const html = [];
    let list = [];
    const inline = (value) => escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    const flush = () => {
      if (list.length) {
        html.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
        list = [];
      }
    };
    for (const line of lines) {
      const bullet = line.match(/^[-*\u2022]\s+(.*)$/);
      if (bullet) {
        list.push(bullet[1]);
      } else {
        flush();
        html.push(`<p>${inline(line)}</p>`);
      }
    }
    flush();
    return html.join("");
  }

  function icon(section, classes = "h-4 w-4") {
    const path = SECTION_ICONS[section] || SECTION_ICONS.header;
    return `<svg class="${classes}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="${path}"/></svg>`;
  }

  function confidenceMeta(score) {
    if (score >= 0.75) return { label: "High", bar: "bg-emerald-500", text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200" };
    if (score >= 0.5) return { label: "Medium", bar: "bg-amber-500", text: "text-amber-700", chip: "bg-amber-50 border-amber-200" };
    return { label: "Low", bar: "bg-rose-500", text: "text-rose-700", chip: "bg-rose-50 border-rose-200" };
  }

  function scrollToBottom() {
    el.conversation.scrollTo({ top: el.conversation.scrollHeight, behavior: "smooth" });
  }

  function setBusy(busy) {
    state.busy = busy;
    el.askButton.disabled = busy;
    el.question.disabled = busy;
    el.employeeSelect.disabled = busy;
    el.askButtonLabel.textContent = busy ? "Thinking..." : "Ask";
    el.conversation.setAttribute("aria-busy", String(busy));
  }

  function renderEngineBadge(health) {
    if (!health) {
      el.engineBadge.className = "inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700";
      el.engineBadge.innerHTML = '<span class="h-2 w-2 rounded-full bg-rose-500"></span> Backend offline';
      return;
    }
    if (health.gemini_configured) {
      el.engineBadge.className = "inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700";
      el.engineBadge.innerHTML = `<span class="h-2 w-2 rounded-full bg-emerald-500"></span> Gemini RAG &middot; ${escapeHtml(health.model)}`;
    } else {
      el.engineBadge.className = "inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700";
      el.engineBadge.innerHTML = '<span class="h-2 w-2 rounded-full bg-amber-500"></span> Offline extractive mode';
      el.engineBadge.title = "Set GEMINI_API_KEY to enable Gemini answers.";
    }
  }

  function renderSuggestions() {
    const chip = (text, compact) =>
      `<button type="button" data-question="${escapeHtml(text)}" class="suggestion rounded-full border border-slate-200 bg-white ${compact ? "px-3 py-1 text-xs" : "px-3.5 py-1.5 text-sm"} text-slate-700 shadow-sm transition hover:border-brand-500 hover:bg-brand-50 hover:text-brand-700">${escapeHtml(text)}</button>`;
    el.suggestions.innerHTML = SUGGESTIONS.map((s) => chip(s, false)).join("");
    el.quickSuggestions.innerHTML = SUGGESTIONS.slice(0, 4).map((s) => chip(s, true)).join("");
  }

  function renderOverview() {
    const latest = state.payslips[state.payslips.length - 1];
    const employee = state.employees.find((e) => e.employee_id === state.employeeId);
    if (!latest) {
      el.overviewNet.textContent = "-";
      el.overviewPeriod.textContent = "No payslips available";
      return;
    }
    el.overviewPeriod.textContent = `${latest.period_label} \u00b7 paid ${new Date(latest.payment_date).toLocaleDateString("en-GB")}`;
    el.overviewNet.textContent = eur.format(latest.net_pay);
    el.overviewEmployee.textContent = employee ? `${employee.full_name} \u00b7 ${employee.job_title}` : latest.full_name;

    const values = {
      gross_salary: eur.format(latest.gross_salary),
      employee_social_security: `- ${eur.format(latest.employee_social_security)}`,
      withholding_tax: `- ${eur.format(latest.withholding_tax)}`,
      meal_vouchers_count: `${latest.meal_vouchers_count} vouchers`,
      remaining_legal_vacation_days: `${latest.remaining_legal_vacation_days.toFixed(1)} days`,
    };
    el.overviewStats.querySelectorAll("[data-field]").forEach((node) => {
      node.textContent = values[node.dataset.field] ?? "-";
    });

    const reversed = [...state.payslips].reverse();
    el.payslipList.innerHTML = reversed
      .map((p, index) => {
        const previous = reversed[index + 1];
        let delta = "";
        if (previous) {
          const diff = p.net_pay - previous.net_pay;
          const up = diff >= 0;
          delta = `<span class="text-xs font-medium ${up ? "text-emerald-600" : "text-rose-600"}">${up ? "\u25b2" : "\u25bc"} ${eur.format(Math.abs(diff))}</span>`;
        }
        return `<li>
          <button type="button" data-period="${escapeHtml(p.period)}" class="open-payslip flex w-full items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-left transition hover:border-brand-500 hover:bg-brand-50">
            <span>
              <span class="block text-sm font-medium text-slate-900">${escapeHtml(p.period_label)}</span>
              <span class="block text-xs text-slate-500">${escapeHtml(p.document_id)}</span>
            </span>
            <span class="text-right">
              <span class="block text-sm font-semibold text-slate-900">${eur.format(p.net_pay)}</span>
              ${delta}
            </span>
          </button>
        </li>`;
      })
      .join("");
  }

  function renderOverviewError(message) {
    el.payslipList.innerHTML = `<li class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">${escapeHtml(message)}</li>`;
  }

  function appendQuestion(question) {
    el.emptyState.classList.add("hidden");
    el.quickSuggestions.classList.remove("hidden");
    el.quickSuggestions.classList.add("flex");
    const node = document.createElement("div");
    node.className = "fade-in flex justify-end";
    node.innerHTML = `<div class="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">${escapeHtml(question)}</div>`;
    el.conversation.appendChild(node);
  }

  function appendLoading() {
    const node = document.createElement("div");
    node.className = "fade-in";
    node.innerHTML = `<div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex items-center gap-3 text-sm text-slate-500">
        <span class="flex gap-1"><span class="typing-dot h-2 w-2 rounded-full bg-brand-500"></span><span class="typing-dot h-2 w-2 rounded-full bg-brand-500"></span><span class="typing-dot h-2 w-2 rounded-full bg-brand-500"></span></span>
        Searching your payslips and preparing a grounded answer...
      </div>
      <div class="mt-4 space-y-2"><div class="h-3 w-5/6 animate-pulse rounded bg-slate-100"></div><div class="h-3 w-2/3 animate-pulse rounded bg-slate-100"></div></div>
    </div>`;
    el.conversation.appendChild(node);
    return node;
  }

  function snippetCard(snippet, amounts) {
    const relevance = Math.round(snippet.relevance * 100);
    const badge = snippet.cited
      ? '<span class="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">Used in answer</span>'
      : '<span class="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">Retrieved</span>';
    return `<article class="overflow-hidden rounded-xl border ${snippet.cited ? "border-emerald-200" : "border-slate-200"} bg-white">
      <header class="flex flex-wrap items-center justify-between gap-2 border-b ${snippet.cited ? "border-emerald-100 bg-emerald-50/70" : "border-slate-100 bg-slate-50"} px-3 py-2">
        <div class="flex items-center gap-2 text-xs">
          <span class="${snippet.cited ? "text-emerald-700" : "text-slate-500"}">${icon(snippet.section)}</span>
          <span class="font-semibold text-slate-800">${escapeHtml(snippet.section_title)}</span>
          <span class="text-slate-400">&middot;</span>
          <span class="text-slate-600">${escapeHtml(snippet.period_label)}</span>
          <span class="text-slate-400">&middot;</span>
          <button type="button" data-period="${escapeHtml(snippet.period)}" class="open-payslip font-mono text-[11px] text-brand-600 hover:underline" title="Open the full payslip">${escapeHtml(snippet.document_id)}</button>
        </div>
        <div class="flex items-center gap-2">
          <span class="flex items-center gap-1.5 text-[11px] text-slate-500" title="Retrieval relevance">
            <span class="h-1.5 w-12 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-brand-500" style="width:${relevance}%"></span></span>
            ${relevance}%
          </span>
          ${badge}
        </div>
      </header>
      <pre class="payslip-text overflow-x-auto px-3 py-2.5 text-[11.5px] leading-relaxed text-slate-800">${highlightSnippet(snippet.text, amounts)}</pre>
      <footer class="border-t border-slate-100 px-3 py-1.5 font-mono text-[10px] text-slate-400">source_id: ${escapeHtml(snippet.source_id)}</footer>
    </article>`;
  }

  function trustBox(response) {
    const amounts = amountsIn(response.answer_summary);
    const cited = response.source_snippets.filter((s) => s.cited);
    const other = response.source_snippets.filter((s) => !s.cited);
    const periods = response.periods_considered.length
      ? response.periods_considered.map((p) => {
          const [y, m] = p.split("-");
          return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
        }).join(", ")
      : "none";

    let body;
    if (!response.source_snippets.length) {
      body = `<p class="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">No payslip text matched this question, so no source could be used. The assistant only answers from your own payslips.</p>`;
    } else {
      const citedHtml = cited.length
        ? cited.map((s) => snippetCard(s, amounts)).join("")
        : `<p class="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">The answer did not rely on any snippet. The text that was searched is listed below.</p>`;
      const otherHtml = other.length
        ? `<details class="group rounded-xl border border-slate-200 bg-white/60">
            <summary class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-600">
              <svg class="chevron h-3.5 w-3.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
              ${other.length} more snippet${other.length > 1 ? "s" : ""} provided as context but not used in the answer
            </summary>
            <div class="space-y-3 px-3 pb-3">${other.map((s) => snippetCard(s, amounts)).join("")}</div>
          </details>`
        : "";
      body = `<div class="space-y-3">${citedHtml}${otherHtml}</div>`;
    }

    return `<section class="mt-4 rounded-2xl border-2 border-emerald-200 bg-emerald-50/40 p-4" aria-label="Trust and transparency">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 class="flex items-center gap-2 text-sm font-semibold text-emerald-900">
          ${icon("social_security", "h-5 w-5 text-emerald-600")}
          Trust &amp; Transparency Box
        </h4>
        <span class="text-xs text-emerald-800">${cited.length} source${cited.length === 1 ? "" : "s"} used &middot; periods searched: ${escapeHtml(periods)}</span>
      </div>
      <p class="mb-3 text-xs text-emerald-800/80">Below is the exact payslip text given to the assistant. Figures that also appear in the answer are <mark class="rounded bg-amber-200 px-1 text-amber-900">highlighted</mark> so you can verify them.</p>
      ${body}
    </section>`;
  }

  function answerCard(response) {
    const conf = confidenceMeta(response.confidence_score);
    const percent = Math.round(response.confidence_score * 100);
    const modeBadge = response.mode === "gemini"
      ? `<span class="rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-medium text-brand-700">Gemini &middot; ${escapeHtml(response.model || "")}</span>`
      : '<span class="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-[11px] font-medium text-amber-700">Offline extractive engine</span>';
    const foundBadge = response.answer_found
      ? '<span class="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700">Answer found in payslip</span>'
      : '<span class="rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-700">Not found in payslip</span>';
    const warnings = response.warnings.length
      ? `<div class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"><ul class="list-disc space-y-0.5 pl-4">${response.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>`
      : "";

    return `<div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">${foundBadge}${modeBadge}<span class="text-[11px] text-slate-400">${response.latency_ms} ms</span></div>
        <div class="flex items-center gap-2 rounded-full border ${conf.chip} px-3 py-1" title="Combined retrieval relevance and model confidence">
          <span class="text-[11px] font-medium ${conf.text}">Confidence ${conf.label}</span>
          <span class="h-1.5 w-16 overflow-hidden rounded-full bg-white"><span class="block h-full rounded-full ${conf.bar}" style="width:${percent}%"></span></span>
          <span class="text-[11px] font-semibold ${conf.text}">${percent}%</span>
        </div>
      </div>
      <div class="answer-text mt-4 text-[15px] leading-relaxed text-slate-800">${renderAnswerText(response.answer_summary)}</div>
      ${warnings}
      ${trustBox(response)}
    </div>`;
  }

  function errorCard(error, question) {
    let detail = "";
    if (Array.isArray(error.detail)) {
      detail = error.detail.map((d) => `${d.field ? `${d.field}: ` : ""}${d.message}`).join("; ");
    } else if (error.detail) {
      detail = String(error.detail);
    }
    return `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800">
      <p class="font-semibold">${escapeHtml(error.message)}</p>
      ${detail ? `<p class="mt-1 text-rose-700">${escapeHtml(detail)}</p>` : ""}
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" data-question="${escapeHtml(question)}" class="suggestion rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700">Try again</button>
        ${error.requestId ? `<span class="font-mono text-[11px] text-rose-500">request id: ${escapeHtml(error.requestId)}</span>` : ""}
      </div>
    </div>`;
  }

  async function ask(question) {
    const trimmed = question.trim();
    if (state.busy) return;
    if (trimmed.length < 3) {
      el.question.focus();
      el.question.classList.add("placeholder:text-rose-400");
      el.question.placeholder = "Please type a question of at least 3 characters.";
      return;
    }
    if (!state.employeeId) return;

    appendQuestion(trimmed);
    el.question.value = "";
    autoResize();
    const loading = appendLoading();
    scrollToBottom();
    setBusy(true);

    try {
      const response = await api("/api/ask", {
        method: "POST",
        body: JSON.stringify({ employee_id: state.employeeId, question: trimmed }),
      });
      loading.innerHTML = answerCard(response);
    } catch (error) {
      loading.innerHTML = errorCard(error instanceof ApiError ? error : new ApiError("Unexpected error. Please try again."), trimmed);
    } finally {
      setBusy(false);
      el.question.focus();
      scrollToBottom();
    }
  }

  async function loadPayslips(employeeId) {
    state.employeeId = employeeId;
    state.payslips = [];
    try {
      state.payslips = await api(`/api/employees/${encodeURIComponent(employeeId)}/payslips`);
      renderOverview();
    } catch (error) {
      renderOverviewError(`Could not load payslips: ${error.message}`);
    }
  }

  function resetConversation() {
    el.conversation.querySelectorAll(":scope > :not(#empty-state)").forEach((node) => node.remove());
    el.emptyState.classList.remove("hidden");
    el.quickSuggestions.classList.add("hidden");
    el.quickSuggestions.classList.remove("flex");
  }

  async function openPayslip(period) {
    if (!state.employeeId) return;
    el.modalTitle.textContent = "Full payslip";
    el.modalSubtitle.textContent = "Loading...";
    el.modalBody.textContent = "";
    el.modal.classList.remove("hidden");
    el.modal.classList.add("flex");
    el.modalClose.focus();
    try {
      const data = await api(`/api/employees/${encodeURIComponent(state.employeeId)}/payslips/${encodeURIComponent(period)}/text`);
      el.modalTitle.textContent = `Full payslip ${data.document_id}`;
      el.modalSubtitle.textContent = "Complete document. Snippets in answers are exact excerpts of this text.";
      el.modalBody.textContent = data.text;
    } catch (error) {
      el.modalSubtitle.textContent = "";
      el.modalBody.textContent = `Could not load the payslip: ${error.message}`;
    }
  }

  function closeModal() {
    el.modal.classList.add("hidden");
    el.modal.classList.remove("flex");
  }

  function autoResize() {
    el.question.style.height = "auto";
    el.question.style.height = `${Math.min(el.question.scrollHeight, 160)}px`;
    el.charCount.textContent = String(el.question.value.length);
  }

  function bindEvents() {
    el.form.addEventListener("submit", (event) => {
      event.preventDefault();
      ask(el.question.value);
    });
    el.question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        ask(el.question.value);
      }
    });
    el.question.addEventListener("input", autoResize);

    document.addEventListener("click", (event) => {
      const suggestion = event.target.closest(".suggestion");
      if (suggestion) {
        ask(suggestion.dataset.question || "");
        return;
      }
      const payslipButton = event.target.closest(".open-payslip");
      if (payslipButton) {
        openPayslip(payslipButton.dataset.period);
      }
    });

    el.employeeSelect.addEventListener("change", async () => {
      resetConversation();
      await loadPayslips(el.employeeSelect.value);
    });

    el.modalClose.addEventListener("click", closeModal);
    el.modal.addEventListener("click", (event) => {
      if (event.target === el.modal) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !el.modal.classList.contains("hidden")) closeModal();
    });
  }

  async function init() {
    renderSuggestions();
    bindEvents();

    api("/api/health").then(renderEngineBadge).catch(() => renderEngineBadge(null));

    try {
      state.employees = await api("/api/employees");
    } catch (error) {
      renderOverviewError(`Could not load employees: ${error.message}`);
      setBusy(true);
      return;
    }
    if (!state.employees.length) {
      renderOverviewError("No employees found.");
      return;
    }
    el.employeeSelect.innerHTML = state.employees
      .map((e) => `<option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.full_name)} (${escapeHtml(e.employee_id)})</option>`)
      .join("");
    await loadPayslips(state.employees[0].employee_id);
    el.question.focus();
  }

  init();
})();
