"use strict";

const API_BASE = "/api/v1";
const HISTORY_KEY = "netprobe:history";
const MAX_HISTORY = 5;

/* ============================================================
   공통 유틸
   ============================================================ */

function qs(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatLocalTime(isoString) {
  try {
    return new Date(isoString).toLocaleString();
  } catch {
    return isoString;
  }
}

/** fetch()를 감싸 공통 응답 봉투를 파싱하고 네트워크 오류를 표준화한다. */
async function callApi(path, { method = "POST", body, signal } = {}) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
    signal,
  };
  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (err) {
    if (err.name === "AbortError") throw err;
    return {
      success: false,
      data: null,
      error: { code: "NETWORK_ERROR", message: "서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요." },
      meta: null,
    };
  }

  let envelope;
  try {
    envelope = await response.json();
  } catch {
    return {
      success: false,
      data: null,
      error: { code: "INTERNAL_SERVER_ERROR", message: "서버 응답을 해석할 수 없습니다." },
      meta: null,
    };
  }
  return envelope;
}

/* ============================================================
   탭 전환
   ============================================================ */

function initTabs() {
  const tabButtons = Array.from(document.querySelectorAll(".tab"));

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
    btn.addEventListener("keydown", (e) => {
      const idx = tabButtons.indexOf(btn);
      if (e.key === "ArrowRight") {
        e.preventDefault();
        tabButtons[(idx + 1) % tabButtons.length].focus();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        tabButtons[(idx - 1 + tabButtons.length) % tabButtons.length].focus();
      }
    });
  });

  function activateTab(name) {
    tabButtons.forEach((btn) => {
      const selected = btn.dataset.tab === name;
      btn.setAttribute("aria-selected", String(selected));
      btn.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      const match = panel.id === `tab-${name}`;
      panel.classList.toggle("is-hidden", !match);
      panel.hidden = !match;
    });
    if (name === "client") {
      loadClientInfo();
    }
  }
}

/* ============================================================
   결과 렌더링 헬퍼
   ============================================================ */

function statusClassForHttp(statusCode, reachable) {
  if (!reachable) return "status-error";
  if (statusCode >= 200 && statusCode < 300) return "status-success";
  if (statusCode >= 300 && statusCode < 400) return "status-info";
  if (statusCode >= 400 && statusCode < 500) return "status-warn";
  if (statusCode >= 500) return "status-caution";
  return "status-info";
}

function renderResultGrid(entries) {
  const items = entries
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(
      ([label, value]) => `
      <div class="result-item">
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value)}</dd>
      </div>`
    )
    .join("");
  return `<dl class="result-grid">${items}</dl>`;
}

function renderResultCard({ statusClass, badgeText, headline, meta, bodyHtml }) {
  return `
    <div class="result-card ${statusClass}">
      <div class="result-headline">
        <span class="status-badge ${statusClass}">${escapeHtml(badgeText)}</span>
        <span class="result-headline-text">${escapeHtml(headline)}</span>
      </div>
      ${meta ? `<div class="result-meta">${escapeHtml(meta)}</div>` : ""}
      ${bodyHtml}
    </div>`;
}

function showResultError(container, envelope) {
  const code = envelope.error ? envelope.error.code : "UNKNOWN_ERROR";
  const message = envelope.error ? envelope.error.message : "알 수 없는 오류가 발생했습니다.";
  const statusClass = code === "VALIDATION_ERROR" || code === "TARGET_NOT_ALLOWED" ? "status-warn" : "status-error";
  container.innerHTML = renderResultCard({
    statusClass,
    badgeText: code,
    headline: message,
    meta: envelope.meta ? `요청 ID ${envelope.meta.request_id}` : "",
    bodyHtml: "",
  });
  focusResult(container);
}

function focusResult(container) {
  container.focus({ preventScroll: false });
}

/* ============================================================
   중복 클릭 방지 + 로딩 상태
   ============================================================ */

function setLoading(button, loading) {
  button.disabled = loading;
  button.classList.toggle("is-loading", loading);
}

/* ============================================================
   이력 저장 (localStorage, 최대 5건)
   ============================================================ */

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistoryEntry(entry) {
  let history = loadHistory();
  history.unshift(entry);
  history = history.slice(0, MAX_HISTORY);
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch {
    /* localStorage 사용 불가 시 조용히 무시 (선택적 기능) */
  }
  renderHistory();
}

function clearHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* no-op */
  }
  renderHistory();
}

function renderHistory() {
  const history = loadHistory();
  qs("history-count").textContent = String(history.length);
  const list = qs("history-list");

  if (history.length === 0) {
    list.innerHTML = `<li class="history-empty">아직 조회 기록이 없습니다.</li>`;
    return;
  }

  list.innerHTML = history
    .map(
      (item) => `
      <li class="history-item">
        <span class="dot ${escapeHtml(item.statusClass)}"></span>
        <span>[${escapeHtml(item.kind)}]</span>
        <span>${escapeHtml(item.summary)}</span>
        <span style="margin-left:auto;color:var(--text-dim)">${escapeHtml(formatLocalTime(item.timestamp))}</span>
      </li>`
    )
    .join("");
}

/* ============================================================
   BE-01. HTTP 상태 확인
   ============================================================ */

let httpAbortController = null;

function initHttpForm() {
  const form = qs("form-http");
  const submitBtn = qs("http-submit");
  const resultArea = qs("http-result");
  const urlInput = qs("http-url");
  const urlError = qs("http-url-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    urlError.textContent = "";
    urlInput.removeAttribute("aria-invalid");

    const url = urlInput.value.trim();
    if (!url) {
      urlError.textContent = "URL을 입력해 주세요.";
      urlInput.setAttribute("aria-invalid", "true");
      urlInput.focus();
      return;
    }
    if (!/^https?:\/\/.+/i.test(url)) {
      urlError.textContent = "http:// 또는 https:// 로 시작하는 URL을 입력해 주세요.";
      urlInput.setAttribute("aria-invalid", "true");
      urlInput.focus();
      return;
    }

    if (httpAbortController) httpAbortController.abort();
    httpAbortController = new AbortController();

    setLoading(submitBtn, true);
    resultArea.innerHTML = `<p class="result-placeholder">진단 중입니다…</p>`;

    const payload = {
      url,
      method: qs("http-method").value,
      timeout_seconds: Number(qs("http-timeout").value) || 5,
      follow_redirects: qs("http-follow").checked,
    };

    const envelope = await callApi("/http-check", { body: payload, signal: httpAbortController.signal });
    setLoading(submitBtn, false);

    if (!envelope.success) {
      showResultError(resultArea, envelope);
      saveHistoryEntry({
        kind: "HTTP",
        summary: `${url} → ${envelope.error ? envelope.error.code : "ERROR"}`,
        statusClass: "status-error",
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const d = envelope.data;
    const statusClass = statusClassForHttp(d.status_code, d.reachable);
    const badge = d.reachable ? `${d.status_code} ${d.reason_phrase || ""}`.trim() : "연결 실패";
    const headline = d.reachable
      ? `연결 성공 · ${d.response_time_ms}ms`
      : "대상에 연결할 수 없습니다.";

    const bodyHtml = renderResultGrid([
      ["최종 URL", d.final_url],
      ["대상 IP", d.resolved_ip],
      ["응답 시간", `${d.response_time_ms} ms`],
      ["콘텐츠 유형", d.content_type],
      ["응답 크기", d.content_length != null ? `${d.content_length} bytes` : null],
      ["리다이렉트 횟수", d.redirect_count],
    ]);

    resultArea.innerHTML = renderResultCard({
      statusClass,
      badgeText: badge || "-",
      headline,
      meta: `요청 ID ${envelope.meta.request_id} · ${formatLocalTime(envelope.meta.timestamp)}`,
      bodyHtml,
    });
    focusResult(resultArea);

    saveHistoryEntry({
      kind: "HTTP",
      summary: `${url} → ${badge}`,
      statusClass,
      timestamp: new Date().toISOString(),
    });
  });
}

/* ============================================================
   BE-02. TCP 포트 확인
   ============================================================ */

let portAbortController = null;

const PORT_RESULT_LABEL = {
  OPEN: "열림",
  REFUSED: "연결 거부",
  TIMEOUT: "응답 없음",
  DNS_FAILED: "DNS 조회 실패",
  BLOCKED: "접근 차단",
};

const PORT_RESULT_STATUS_CLASS = {
  OPEN: "status-success",
  REFUSED: "status-warn",
  TIMEOUT: "status-caution",
  DNS_FAILED: "status-error",
  BLOCKED: "status-error",
};

function initPortForm() {
  const form = qs("form-port");
  const submitBtn = qs("port-submit");
  const resultArea = qs("port-result");
  const hostInput = qs("port-host");
  const hostError = qs("port-host-error");
  const portInput = qs("port-port");
  const portError = qs("port-port-error");

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      portInput.value = chip.dataset.port;
      portInput.focus();
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hostError.textContent = "";
    portError.textContent = "";
    hostInput.removeAttribute("aria-invalid");
    portInput.removeAttribute("aria-invalid");

    const host = hostInput.value.trim();
    const port = Number(portInput.value);

    let hasError = false;
    if (!host) {
      hostError.textContent = "호스트를 입력해 주세요.";
      hostInput.setAttribute("aria-invalid", "true");
      hasError = true;
    }
    if (!port || port < 1 || port > 65535) {
      portError.textContent = "포트는 1~65535 사이의 숫자여야 합니다.";
      portInput.setAttribute("aria-invalid", "true");
      hasError = true;
    }
    if (hasError) {
      (hostError.textContent ? hostInput : portInput).focus();
      return;
    }

    if (portAbortController) portAbortController.abort();
    portAbortController = new AbortController();

    setLoading(submitBtn, true);
    resultArea.innerHTML = `<p class="result-placeholder">진단 중입니다…</p>`;

    const payload = {
      host,
      port,
      timeout_seconds: Number(qs("port-timeout").value) || 3,
    };

    const envelope = await callApi("/port-check", { body: payload, signal: portAbortController.signal });
    setLoading(submitBtn, false);

    if (!envelope.success) {
      showResultError(resultArea, envelope);
      saveHistoryEntry({
        kind: "PORT",
        summary: `${host}:${port} → ${envelope.error ? envelope.error.code : "ERROR"}`,
        statusClass: "status-error",
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const d = envelope.data;
    const statusClass = PORT_RESULT_STATUS_CLASS[d.result] || "status-info";
    const badge = PORT_RESULT_LABEL[d.result] || d.result;

    const bodyHtml = renderResultGrid([
      ["변환된 IP", (d.resolved_ips || []).join(", ")],
      ["연결 시간", d.connection_time_ms != null ? `${d.connection_time_ms} ms` : null],
      ["설명", d.message],
    ]);

    resultArea.innerHTML = renderResultCard({
      statusClass,
      badgeText: badge,
      headline: `${host}:${port}`,
      meta: `요청 ID ${envelope.meta.request_id} · ${formatLocalTime(envelope.meta.timestamp)}`,
      bodyHtml,
    });
    focusResult(resultArea);

    saveHistoryEntry({
      kind: "PORT",
      summary: `${host}:${port} → ${badge}`,
      statusClass,
      timestamp: new Date().toISOString(),
    });
  });
}

/* ============================================================
   BE-03. DNS 조회
   ============================================================ */

let dnsAbortController = null;

function initDnsForm() {
  const form = qs("form-dns");
  const submitBtn = qs("dns-submit");
  const resultArea = qs("dns-result");
  const domainInput = qs("dns-domain");
  const domainError = qs("dns-domain-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    domainError.textContent = "";
    domainInput.removeAttribute("aria-invalid");

    const domain = domainInput.value.trim();
    if (!domain || /^https?:\/\//i.test(domain) || domain.includes("/")) {
      domainError.textContent = "스킴과 경로 없이 순수 도메인만 입력해 주세요. 예: example.com";
      domainInput.setAttribute("aria-invalid", "true");
      domainInput.focus();
      return;
    }

    if (dnsAbortController) dnsAbortController.abort();
    dnsAbortController = new AbortController();

    setLoading(submitBtn, true);
    resultArea.innerHTML = `<p class="result-placeholder">조회 중입니다…</p>`;

    const recordType = qs("dns-type").value;
    const payload = { domain, record_type: recordType };

    const envelope = await callApi("/dns-lookup", { body: payload, signal: dnsAbortController.signal });
    setLoading(submitBtn, false);

    if (!envelope.success) {
      showResultError(resultArea, envelope);
      saveHistoryEntry({
        kind: "DNS",
        summary: `${domain} (${recordType}) → ${envelope.error ? envelope.error.code : "ERROR"}`,
        statusClass: "status-error",
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const d = envelope.data;
    const hasRecords = d.records && d.records.length > 0;
    const statusClass = hasRecords ? "status-success" : "status-warn";
    const badge = hasRecords ? `${d.records.length}건` : "결과 없음";

    const rows = hasRecords
      ? d.records.map((rec) => `<tr><td>${escapeHtml(rec)}</td></tr>`).join("")
      : `<tr><td>해당 유형의 레코드가 없습니다.</td></tr>`;

    const bodyHtml = `
      <div class="result-grid" style="margin-bottom:8px">
        <div class="result-item"><dt>TTL</dt><dd>${d.ttl != null ? escapeHtml(d.ttl) : "-"}</dd></div>
        <div class="result-item"><dt>조회 시간</dt><dd>${escapeHtml(d.lookup_time_ms)} ms</dd></div>
        <div class="result-item"><dt>리졸버</dt><dd>${d.resolver ? escapeHtml(d.resolver) : "-"}</dd></div>
      </div>
      <table class="data-table">
        <thead><tr><th>${escapeHtml(recordType)} 레코드</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    resultArea.innerHTML = renderResultCard({
      statusClass,
      badgeText: badge,
      headline: `${domain} · ${recordType}`,
      meta: `요청 ID ${envelope.meta.request_id} · ${formatLocalTime(envelope.meta.timestamp)}`,
      bodyHtml,
    });
    focusResult(resultArea);

    saveHistoryEntry({
      kind: "DNS",
      summary: `${domain} (${recordType}) → ${badge}`,
      statusClass,
      timestamp: new Date().toISOString(),
    });
  });
}

/* ============================================================
   BE-04. 접속 정보
   ============================================================ */

let clientInfoLoading = false;

async function loadClientInfo() {
  if (clientInfoLoading) return;
  clientInfoLoading = true;

  const resultArea = qs("client-result");
  resultArea.innerHTML = `<p class="result-placeholder">접속 정보를 불러오는 중입니다…</p>`;

  const envelope = await callApi("/client-info", { method: "GET" });
  clientInfoLoading = false;

  if (!envelope.success) {
    showResultError(resultArea, envelope);
    return;
  }

  const d = envelope.data;
  const bodyHtml = renderResultGrid([
    ["접속 IP", d.client_ip],
    ["프록시 전달 IP", (d.forwarded_for || []).join(", ") || "없음"],
    ["User-Agent", d.user_agent],
    ["언어", d.accept_language],
    ["프로토콜", d.protocol],
    ["접속 방식", d.scheme],
    ["Host", d.host],
  ]);

  resultArea.innerHTML = renderResultCard({
    statusClass: "status-info",
    badgeText: "접속 정보",
    headline: d.client_ip,
    meta: `요청 ID ${envelope.meta.request_id} · ${formatLocalTime(envelope.meta.timestamp)}`,
    bodyHtml,
  });
}

function initClientInfoTab() {
  qs("client-refresh").addEventListener("click", loadClientInfo);
}

/* ============================================================
   초기화
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initHttpForm();
  initPortForm();
  initDnsForm();
  initClientInfoTab();
  renderHistory();
  qs("history-clear").addEventListener("click", clearHistory);
});
