const SESSION_USER_KEY = "gateway-portal-user-name";
const SESSION_API_KEY = "gateway-portal-api-key";

const state = {
  userName: window.sessionStorage.getItem(SESSION_USER_KEY) || "",
  apiKey: "",  // Never loaded from storage — memory only
  isAdmin: false,
  refreshTimer: null,
  lastCustomerApiKey: "",
};

const elements = {
  loginForm: document.getElementById("login-form"),
  loginUserName: document.getElementById("login-user-name"),
  loginApiKey: document.getElementById("login-api-key"),
  fillDemoUser: document.getElementById("fill-demo-user"),
  fillDemoAdmin: document.getElementById("fill-demo-admin"),
  loginStatus: document.getElementById("login-status"),
  appShell: document.getElementById("app-shell"),
  sessionUserName: document.getElementById("session-user-name"),
  sessionMeta: document.getElementById("session-meta"),
  refreshButton: document.getElementById("refresh-button"),
  logoutButton: document.getElementById("logout-button"),
  metricBalance: document.getElementById("metric-balance"),
  metricRequests: document.getElementById("metric-requests"),
  metricTokens: document.getElementById("metric-tokens"),
  metricCost: document.getElementById("metric-cost"),
  accountUserName: document.getElementById("account-user-name"),
  accountKeyPrefix: document.getElementById("account-key-prefix"),
  accountRole: document.getElementById("account-role"),
  accountBalance: document.getElementById("account-balance"),
  requestsTableBody: document.getElementById("requests-table-body"),
  ledgerTableBody: document.getElementById("ledger-table-body"),
  playgroundForm: document.getElementById("playground-form"),
  playgroundModel: document.getElementById("playground-model"),
  playgroundPrompt: document.getElementById("playground-prompt"),
  playgroundTemperature: document.getElementById("playground-temperature"),
  playgroundMaxTokens: document.getElementById("playground-max-tokens"),
  playgroundStatus: document.getElementById("playground-status"),
  playgroundResponse: document.getElementById("playground-response"),
  adminShell: document.getElementById("admin-shell"),
  customerForm: document.getElementById("customer-form"),
  customerName: document.getElementById("customer-name"),
  customerDescription: document.getElementById("customer-description"),
  customerPayment: document.getElementById("customer-payment"),
  customerMargin: document.getElementById("customer-margin"),
  customerStatus: document.getElementById("customer-status"),
  customerResult: document.getElementById("customer-result"),
  customerApiKey: document.getElementById("customer-api-key"),
  copyApiKeyButton: document.getElementById("copy-api-key-button"),
  topupForm: document.getElementById("topup-form"),
  topupUserId: document.getElementById("topup-user-id"),
  topupPayment: document.getElementById("topup-payment"),
  topupMargin: document.getElementById("topup-margin"),
  topupGrantedPreview: document.getElementById("topup-granted-preview"),
  topupStatus: document.getElementById("topup-status"),
  usersTableBody: document.getElementById("users-table-body"),
  toast: document.getElementById("toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMoney(value) {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatInteger(value) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString("zh-CN", {
        hour12: false,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function setSession(userName, apiKey) {
  state.userName = userName.trim();
  state.apiKey = apiKey.trim();
  // API key is kept in memory only — never persisted to storage
  if (state.userName) {
    window.sessionStorage.setItem(SESSION_USER_KEY, state.userName);
  } else {
    window.sessionStorage.removeItem(SESSION_USER_KEY);
  }
  // Intentionally NOT storing apiKey in sessionStorage to prevent
  // XSS / browser extension theft. Users must re-enter key on refresh.
  window.sessionStorage.removeItem(SESSION_API_KEY);
}

function showToast(message, kind = "info") {
  elements.toast.textContent = message;
  elements.toast.className = `toast ${kind}`;
  elements.toast.hidden = false;
  window.clearTimeout(showToast.timerId);
  showToast.timerId = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 3200);
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function apiFetch(path, options = {}) {
  if (!state.apiKey) {
    throw new Error("请先登录。");
  }

  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${state.apiKey}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await window.fetch(path, { ...options, headers });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response;
}

function renderEmptyRow(columns, text) {
  return `<tr><td colspan="${columns}" class="helper-text">${escapeHtml(text)}</td></tr>`;
}

function renderDashboard(dashboard) {
  state.isAdmin = Boolean(dashboard.is_admin);
  elements.appShell.hidden = false;
  elements.adminShell.hidden = !state.isAdmin;

  elements.sessionUserName.textContent = dashboard.user_name;
  elements.sessionMeta.textContent = `${state.isAdmin ? "管理员" : "普通用户"} · key 前缀 ${dashboard.key_prefix}`;

  elements.metricBalance.textContent = `${formatMoney(dashboard.balance)} CNY`;
  elements.metricRequests.textContent = formatInteger(dashboard.usage_summary.request_count);
  elements.metricTokens.textContent = formatInteger(dashboard.usage_summary.total_tokens);
  elements.metricCost.textContent = `${formatMoney(dashboard.usage_summary.billed_amount)} CNY`;

  elements.accountUserName.textContent = dashboard.user_name;
  elements.accountKeyPrefix.textContent = dashboard.key_prefix;
  elements.accountRole.textContent = state.isAdmin ? "管理员" : "普通用户";
  elements.accountBalance.textContent = `${formatMoney(dashboard.balance)} CNY`;

  elements.requestsTableBody.innerHTML = dashboard.recent_requests.length
    ? dashboard.recent_requests
        .map(
          (item) => `
            <tr>
              <td>${escapeHtml(formatDateTime(item.created_at))}</td>
              <td>${escapeHtml(item.model)}</td>
              <td>${escapeHtml(item.status_code)}</td>
              <td>${escapeHtml(formatInteger(item.total_tokens))}</td>
              <td>${escapeHtml(formatMoney(item.billed_amount))}</td>
            </tr>
          `
        )
        .join("")
    : renderEmptyRow(5, "暂无请求记录。");

  elements.ledgerTableBody.innerHTML = dashboard.recent_ledger.length
    ? dashboard.recent_ledger
        .map((item) => {
          const amountClass = Number(item.amount) >= 0 ? "value-positive" : "value-negative";
          return `
            <tr>
              <td>${escapeHtml(formatDateTime(item.created_at))}</td>
              <td>${escapeHtml(item.transaction_type)}</td>
              <td class="${amountClass}">${escapeHtml(formatMoney(item.amount))}</td>
              <td>${escapeHtml(formatMoney(item.balance_after))}</td>
            </tr>
          `;
        })
        .join("")
    : renderEmptyRow(4, "暂无账本记录。");

  if (!elements.playgroundModel.value) {
    elements.playgroundModel.value = "gpt-4o-mini";
  }
}

function populateUsers(users) {
  elements.topupUserId.innerHTML = users.length
    ? users
        .map(
          (user) =>
            `<option value="${escapeHtml(user.user_id)}">${escapeHtml(user.user_name)} · 余额 ${escapeHtml(formatMoney(user.balance))}</option>`
        )
        .join("")
    : '<option value="">暂无用户</option>';
}

function renderUsersTable(rows) {
  elements.usersTableBody.innerHTML = rows.length
    ? rows
        .map(
          (row) => `
            <tr>
              <td>${escapeHtml(row.user_name)}</td>
              <td>${escapeHtml(formatMoney(row.remaining_balance))}</td>
              <td>${escapeHtml(formatInteger(row.request_count))}</td>
              <td>${escapeHtml(formatInteger(row.total_tokens))}</td>
              <td>${escapeHtml(formatMoney(row.billed_amount))}</td>
              <td>${escapeHtml(formatInteger(row.active_api_key_count))}</td>
            </tr>
          `
        )
        .join("")
    : renderEmptyRow(6, "暂无用户数据。");
}

async function loadAdminData() {
  const [usersResponse, usageResponse] = await Promise.all([apiFetch("/admin/users"), apiFetch("/admin/usage/users")]);
  const [users, usageRows] = await Promise.all([usersResponse.json(), usageResponse.json()]);
  populateUsers(users);
  renderUsersTable(usageRows);
}

async function refreshDashboard() {
  const response = await apiFetch("/v1/me/dashboard");
  const dashboard = await response.json();
  renderDashboard(dashboard);
  if (state.isAdmin) {
    await loadAdminData();
  }
}

function resetApp() {
  setSession("", "");
  state.isAdmin = false;
  state.lastCustomerApiKey = "";
  window.clearInterval(state.refreshTimer);
  state.refreshTimer = null;
  elements.appShell.hidden = true;
  elements.adminShell.hidden = true;
  elements.loginUserName.value = "";
  elements.loginApiKey.value = "";
  elements.loginStatus.textContent = "首次登录后会保存在当前浏览器会话里。";
  elements.playgroundResponse.textContent = "这里显示模型回复和 usage。";
}

function ensureAutoRefresh() {
  window.clearInterval(state.refreshTimer);
  state.refreshTimer = window.setInterval(() => {
    refreshDashboard().catch(() => {});
  }, 15000);
}

function updateGrantedPreview() {
  const payment = Number(elements.topupPayment.value || 0);
  const margin = Number(elements.topupMargin.value || 0);
  const granted = Math.max(0, payment - margin);
  elements.topupGrantedPreview.value = granted.toFixed(2);
}

async function handleLogin(event) {
  event.preventDefault();
  const userName = elements.loginUserName.value.trim();
  const apiKey = elements.loginApiKey.value.trim();
  if (!userName || !apiKey) {
    showToast("请输入用户名和 API key。", "error");
    return;
  }

  elements.loginStatus.textContent = "登录中...";
  const response = await window.fetch("/v1/portal/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_name: userName, api_key: apiKey }),
  });
  if (!response.ok) {
    const error = await parseError(response);
    elements.loginStatus.textContent = error;
    showToast(error, "error");
    return;
  }

  const dashboard = await response.json();
  setSession(userName, apiKey);
  renderDashboard(dashboard);
  if (dashboard.is_admin) {
    await loadAdminData();
  }
  ensureAutoRefresh();
  elements.loginStatus.textContent = "登录成功。";
  showToast("登录成功。");
}

async function handlePlaygroundSubmit(event) {
  event.preventDefault();
  const prompt = elements.playgroundPrompt.value.trim();
  if (!prompt) {
    showToast("请输入消息内容。", "error");
    return;
  }

  elements.playgroundStatus.textContent = "发送中...";
  try {
    const response = await apiFetch("/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({
        model: elements.playgroundModel.value.trim(),
        temperature: Number(elements.playgroundTemperature.value),
        max_tokens: Number(elements.playgroundMaxTokens.value),
        messages: [{ role: "user", content: prompt }],
      }),
    });
    const payload = await response.json();
    const message = payload.choices?.[0]?.message?.content || "模型已返回，但没有标准文本内容。";
    elements.playgroundResponse.textContent = `${message}\n\nUsage\n${JSON.stringify(payload.usage || {}, null, 2)}`;
    elements.playgroundPrompt.value = "";
    elements.playgroundStatus.textContent = "发送成功。";
    await refreshDashboard();
  } catch (error) {
    elements.playgroundStatus.textContent = error.message;
    showToast(error.message, "error");
  }
}

async function handleCustomerCreate(event) {
  event.preventDefault();
  elements.customerStatus.textContent = "创建中...";
  try {
    const response = await apiFetch("/admin/customers", {
      method: "POST",
      body: JSON.stringify({
        name: elements.customerName.value.trim(),
        description: elements.customerDescription.value.trim() || null,
        payment_amount: Number(elements.customerPayment.value).toFixed(2),
        margin_amount: Number(elements.customerMargin.value).toFixed(2),
      }),
    });
    const payload = await response.json();
    state.lastCustomerApiKey = payload.api_key;
    elements.customerApiKey.textContent = payload.api_key;
    elements.customerResult.hidden = false;
    elements.customerStatus.textContent = `已创建 ${payload.user_id}，每个用户都会生成不同 key。`;
    elements.customerForm.reset();
    elements.customerPayment.value = "200.00";
    elements.customerMargin.value = "40.00";
    await refreshDashboard();
    showToast("新用户已创建。");
  } catch (error) {
    elements.customerStatus.textContent = error.message;
    showToast(error.message, "error");
  }
}

async function handleTopup(event) {
  event.preventDefault();
  if (!elements.topupUserId.value) {
    showToast("请先选择用户。", "error");
    return;
  }

  elements.topupStatus.textContent = "充值中...";
  try {
    const response = await apiFetch("/admin/topups", {
      method: "POST",
      body: JSON.stringify({
        user_id: elements.topupUserId.value,
        payment_amount: Number(elements.topupPayment.value).toFixed(2),
        margin_amount: Number(elements.topupMargin.value).toFixed(2),
      }),
    });
    const payload = await response.json();
    elements.topupStatus.textContent = `${payload.user_name} 当前余额 ${formatMoney(payload.balance)} CNY`;
    await refreshDashboard();
    showToast("充值成功。");
  } catch (error) {
    elements.topupStatus.textContent = error.message;
    showToast(error.message, "error");
  }
}

async function handleCopyKey() {
  if (!state.lastCustomerApiKey) {
    return;
  }
  try {
    await navigator.clipboard.writeText(state.lastCustomerApiKey);
    showToast("新用户 key 已复制。");
  } catch {
    showToast("复制失败，请手动复制。", "error");
  }
}

function bindEvents() {
  elements.loginForm.addEventListener("submit", (event) => {
    handleLogin(event).catch((error) => {
      elements.loginStatus.textContent = error.message;
      showToast(error.message, "error");
    });
  });
  elements.fillDemoUser.addEventListener("click", () => {
    elements.loginUserName.value = "demo-user";
    elements.loginApiKey.value = "gw_demo_local_key";
  });
  elements.fillDemoAdmin.addEventListener("click", () => {
    elements.loginUserName.value = "admin-user";
    elements.loginApiKey.value = "gw_admin_local_key";
  });
  elements.refreshButton.addEventListener("click", () => {
    refreshDashboard().catch((error) => showToast(error.message, "error"));
  });
  elements.logoutButton.addEventListener("click", () => {
    resetApp();
    showToast("已退出登录。");
  });
  elements.playgroundForm.addEventListener("submit", handlePlaygroundSubmit);
  elements.customerForm.addEventListener("submit", handleCustomerCreate);
  elements.topupForm.addEventListener("submit", handleTopup);
  elements.topupPayment.addEventListener("input", updateGrantedPreview);
  elements.topupMargin.addEventListener("input", updateGrantedPreview);
  elements.copyApiKeyButton.addEventListener("click", handleCopyKey);
}

async function bootstrap() {
  bindEvents();
  updateGrantedPreview();
  if (!state.userName || !state.apiKey) {
    return;
  }

  elements.loginUserName.value = state.userName;
  elements.loginApiKey.value = state.apiKey;
  try {
    await refreshDashboard();
    ensureAutoRefresh();
    elements.loginStatus.textContent = "已自动恢复上次登录。";
  } catch {
    resetApp();
  }
}

bootstrap();
