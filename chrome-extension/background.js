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
      throw new Error("Abra uma página HTTPS de vaga em Gupy, Vagas.com, InfoJobs, Catho, Sólides ou Empregos.com.br.");
    }
    return url.hostname.toLowerCase();
  }

  function requirePopupSender(sender) {
    if (sender?.url !== chrome.runtime.getURL("popup.html")) {
      throw new Error("Abra o complemento pelo ícone do navegador para continuar.");
    }
  }

  async function requireActiveSidePanelTab(message, sender) {
    if (sender?.url !== chrome.runtime.getURL("sidepanel.html")) {
      throw new Error("Abra a cópia rápida pelo complemento para analisar a vaga.");
    }
    const tabId = Number(message.tabId);
    if (!Number.isSafeInteger(tabId) || tabId < 0) throw new Error("A vaga ativa não está disponível.");
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab?.id || activeTab.id !== tabId) throw new Error("Volte à vaga escolhida e tente novamente.");
    const tab = await chrome.tabs.get(tabId);
    const host = activeSupportedHost({ tab });
    return { tab, host };
  }

  function autoWidgetScriptId(host) {
    return `cc-job-widget-${host.replace(/\./g, "_").replace(/[^a-z0-9_-]/g, "_")}`;
  }

  async function requireActivePopupTab(message) {
    const tabId = Number(message.tabId);
    if (!Number.isSafeInteger(tabId) || tabId < 0) throw new Error("A página ativa não está disponível.");
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab?.id || activeTab.id !== tabId) throw new Error("Volte à vaga escolhida e reabra o complemento.");
    const host = activeSupportedHost({ tab: activeTab });
    return { tab: activeTab, host, originPattern: `https://${host}/*` };
  }

  async function autoWidgetState(host) {
    const id = autoWidgetScriptId(host);
    const [script] = await chrome.scripting.getRegisteredContentScripts({ ids: [id] });
    const originPattern = `https://${host}/*`;
    const permitted = await chrome.permissions.contains({ origins: [originPattern] });
    return { enabled: Boolean(script), permission_granted: permitted, host };
  }

  async function setAutoWidget(message, enabled) {
    requirePopupSender(message.sender);
    const { tab, host, originPattern } = await requireActivePopupTab(message);
    const id = autoWidgetScriptId(host);
    const [script] = await chrome.scripting.getRegisteredContentScripts({ ids: [id] });
    if (enabled) {
      const permitted = await chrome.permissions.contains({ origins: [originPattern] });
      if (!permitted) throw new Error("Conceda a permissão do Chrome para ativar o botão automático neste domínio.");
      const registration = {
        id,
        matches: [originPattern],
        js: ["job-page-policy.js", "job-context.js", "portal-selectors.js", "field-filler.js", "copilot-widget.js"],
        runAt: "document_idle",
        persistAcrossSessions: true,
      };
      if (script) await chrome.scripting.updateContentScripts([registration]);
      else await chrome.scripting.registerContentScripts([registration]);
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["job-page-policy.js", "job-context.js", "portal-selectors.js", "field-filler.js", "copilot-widget.js"],
      });
      return { enabled: true, host };
    }

    if (script) await chrome.scripting.unregisterContentScripts({ ids: [id] });
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          globalThis.__ccCopilotWidgetDismissed = true;
          globalThis.__ccCopilotWidgetDispose?.();
          if (globalThis.__ccAutofillMessageListener) {
            chrome.runtime.onMessage.removeListener(globalThis.__ccAutofillMessageListener);
            delete globalThis.__ccAutofillMessageListener;
          }
          globalThis.__ccAutofillListenerInstalled = false;
          delete globalThis.CandidaturaCertaFieldFiller;
        },
      });
    } catch { /* a permissão da página pode já ter sido revogada */ }
    return { enabled: false, host };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const operation = message?.type;
    if (!["CC_GET_STATUS", "CC_GET_PROFILE", "CC_PREPARE_PROFILE", "CC_ANALYZE_JOB", "CC_COMPLETE_PREPARATION", "CC_LIST_DOCUMENTS", "CC_GET_APPLICATION_PDFS", "CC_GET_AUTO_WIDGET_STATUS", "CC_ENABLE_AUTO_WIDGET", "CC_DISABLE_AUTO_WIDGET"].includes(operation)) return false;

    (async () => {
      if (operation === "CC_GET_STATUS") return { ok: true, value: await apiRequest("/api/copilot/status") };
      if (operation === "CC_GET_PROFILE") return { ok: true, value: await apiRequest("/api/copilot/profile") };
      if (operation === "CC_GET_AUTO_WIDGET_STATUS") {
        requirePopupSender(sender);
        const { host } = await requireActivePopupTab(message);
        return { ok: true, value: await autoWidgetState(host) };
      }
      if (operation === "CC_ENABLE_AUTO_WIDGET" || operation === "CC_DISABLE_AUTO_WIDGET") {
        return { ok: true, value: await setAutoWidget({ ...message, sender }, operation === "CC_ENABLE_AUTO_WIDGET") };
      }
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
        const jobContext = message.jobContext && typeof message.jobContext === "object" ? message.jobContext : {};
        const value = await apiRequest("/api/copilot/prepare", {
          method: "POST",
          body: {
            request_id: message.requestId,
            portal_host: portalHost,
            portal_allowed: true,
            job_title: typeof jobContext.title === "string" ? jobContext.title.slice(0, 200) : "",
            job_company: typeof jobContext.company === "string" ? jobContext.company.slice(0, 200) : "",
            job_location: typeof jobContext.location === "string" ? jobContext.location.slice(0, 200) : "",
            job_description: typeof jobContext.description === "string" ? jobContext.description.slice(0, 12000) : "",
          },
        });
        return { ok: true, value };
      }
      if (operation === "CC_ANALYZE_JOB") {
        const { host } = await requireActiveSidePanelTab(message, sender);
        if (message.consent !== true) throw new Error("Autorize o envio dos dados para analisar a vaga.");
        const jobContext = message.jobContext && typeof message.jobContext === "object" ? message.jobContext : {};
        if (typeof jobContext.description !== "string" || jobContext.description.trim().length < 80) {
          throw new Error("Não encontrei uma descrição de vaga visível nesta página. Nenhum dado foi enviado.");
        }
        const value = await apiRequest("/api/copilot/prepare", {
          method: "POST",
          body: {
            request_id: message.requestId,
            portal_host: host,
            portal_allowed: false,
            analysis_only: true,
            consent_data_processing: true,
            consent_gemini_processing: message.useGemini === true,
            job_title: typeof jobContext.title === "string" ? jobContext.title.slice(0, 200) : "",
            job_company: typeof jobContext.company === "string" ? jobContext.company.slice(0, 200) : "",
            job_location: typeof jobContext.location === "string" ? jobContext.location.slice(0, 200) : "",
            job_description: jobContext.description.slice(0, 12000),
          },
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
