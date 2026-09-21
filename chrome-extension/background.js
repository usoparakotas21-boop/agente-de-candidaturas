importScripts("automation-policy.js");

(() => {
  const APP_ORIGINS = [
    "https://candidaturacerta.com.br",
    "https://agente-de-candidaturas.onrender.com",
  ];
  const ACCESS_COOKIE = "agente_access_token";

  async function ensureAccountPermission() {
    const permitted = await chrome.permissions.contains({
      permissions: ["cookies"],
      origins: APP_ORIGINS.map(origin => `${origin}/*`),
    });
    if (!permitted) throw new Error("Conecte sua conta e autorize o acesso ao domínio da Candidatura Certa.");
  }

  async function sessionHeaders() {
    await ensureAccountPermission();
    for (const origin of APP_ORIGINS) {
      const access = await chrome.cookies.get({ url: `${origin}/`, name: ACCESS_COOKIE });
      if (access?.value) {
        const headers = {};
        headers.Authorization = `Bearer ${access.value}`;
        return headers;
      }
    }
    {
      throw new Error("Entre em candidaturacerta.com.br e conecte o complemento novamente.");
    }
  }

  async function apiRequest(path, { method = "GET", body } = {}) {
    const headers = await sessionHeaders();
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetch(`https://candidaturacerta.com.br${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
      });
    } catch {
      throw new Error("Não foi possível conectar à Candidatura Certa. Confira sua internet e tente novamente.");
    }
    let payload = {};
    try { payload = await response.json(); } catch { /* resposta sem JSON */ }
    if (!response.ok) {
      const detail = typeof payload.detail === "string" ? payload.detail : "A solicitação não foi autorizada.";
      throw new Error(detail);
    }
    return payload;
  }

  function activeSupportedHost(sender) {
    let url;
    try { url = new URL(sender?.tab?.url || ""); } catch { throw new Error("Abra uma vaga segura em uma aba do Chrome."); }
    if (url.protocol !== "https:") throw new Error("O copiloto só funciona em páginas HTTPS.");
    if (!globalThis.CandidaturaCertaAutomationPolicy.isSupportedAutomationHost(url.hostname)) {
      if (globalThis.CandidaturaCertaAutomationPolicy.isRestrictedAutomationHost(url.hostname)) {
        throw new Error(globalThis.CandidaturaCertaAutomationPolicy.restrictedMessageFor(url.hostname));
      }
      throw new Error("Nesta versão, o copiloto funciona em páginas de vagas da Gupy, Vagas.com e InfoJobs.");
    }
    return url.hostname.toLowerCase();
  }

  function requirePopupSender(sender) {
    if (sender?.url !== chrome.runtime.getURL("popup.html")) {
      throw new Error("Abra o complemento pelo ícone do navegador para continuar.");
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const operation = message?.type;
    if (!["CC_GET_STATUS", "CC_GET_PROFILE", "CC_PREPARE_PROFILE", "CC_COMPLETE_PREPARATION", "CC_LIST_DOCUMENTS", "CC_GET_APPLICATION_PDFS"].includes(operation)) return false;

    (async () => {
      if (operation === "CC_GET_STATUS") return { ok: true, value: await apiRequest("/api/copilot/status") };
      if (operation === "CC_GET_PROFILE") return { ok: true, value: await apiRequest("/api/copilot/profile") };
      if (operation === "CC_LIST_DOCUMENTS") {
        requirePopupSender(sender);
        return { ok: true, value: await apiRequest("/api/copilot/documents") };
      }
      if (operation === "CC_GET_APPLICATION_PDFS") {
        requirePopupSender(sender);
        const tab = await chrome.tabs.get(Number(message.tabId));
        activeSupportedHost({ tab });
        const applicationId = Number(message.applicationId);
        if (!Number.isSafeInteger(applicationId) || applicationId < 1) throw new Error("Selecione uma candidatura salva.");
        return { ok: true, value: await apiRequest(`/api/copilot/documents/${applicationId}/pdfs`) };
      }
      if (operation === "CC_PREPARE_PROFILE") {
        const portalHost = activeSupportedHost(sender);
        if (message.portalAllowed !== true) throw new Error("Confirme que o portal permite preenchimento assistido.");
        const value = await apiRequest("/api/copilot/prepare", {
          method: "POST",
          body: { request_id: message.requestId, portal_host: portalHost, portal_allowed: true },
        });
        return { ok: true, value };
      }
      if (!sender?.tab?.id) throw new Error("A preparação precisa continuar na aba da vaga.");
      const value = await apiRequest("/api/copilot/complete", {
        method: "POST",
        body: { request_id: message.requestId, filled_count: message.filledCount },
      });
      return { ok: true, value };
    })().then(sendResponse).catch(error => {
      sendResponse({ ok: false, message: error instanceof Error ? error.message : "Não foi possível concluir a ação." });
    });
    return true;
  });

  if (chrome.sidePanel?.setOptions) {
    chrome.sidePanel.setOptions({ path: "sidepanel.html", enabled: true }).catch(() => {});
  }
})();
