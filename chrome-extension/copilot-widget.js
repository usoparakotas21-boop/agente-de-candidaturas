(() => {
  if (!document.body) return;
  const pagePolicy = globalThis.CandidaturaCertaJobPagePolicy;
  if (!pagePolicy?.isLikelyJobPage) return;
  let observer = null;
  let pendingCheck = null;

  function mountWidget() {
    if (globalThis.__ccCopilotWidgetInstalled || globalThis.__ccCopilotWidgetDismissed || !document.body) return;
    globalThis.__ccCopilotWidgetInstalled = true;

  const host = document.createElement("div");
  host.id = "cc-copilot-widget-host";
  host.setAttribute("aria-label", "Copiloto da Candidatura Certa");
  const shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    :host{all:initial}*{box-sizing:border-box;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
    .launcher{position:fixed;right:22px;bottom:22px;z-index:2147483647;border:0;border-radius:999px;padding:12px 18px;background:#153a70;color:#fff;font-size:14px;font-weight:750;box-shadow:0 8px 26px #10213d44;cursor:pointer}
    .launcher:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #ffbf47;outline-offset:3px}
    .panel{position:fixed;right:22px;bottom:82px;z-index:2147483647;width:min(360px,calc(100vw - 32px));padding:18px;border:1px solid #dce5f2;border-radius:16px;background:#fff;color:#152b49;box-shadow:0 16px 48px #10213d33}
    .panel[hidden]{display:none}.heading{margin:0;font-size:16px}.copy{margin:8px 0 14px;color:#52657e;font-size:12px;line-height:1.5}
    .consent{display:flex;align-items:flex-start;gap:8px;margin:0 0 12px;padding:10px;border-radius:10px;background:#eff5ff;font-size:12px;line-height:1.4}.consent input{margin:2px 0 0;flex:none}
    .actions{display:flex;gap:8px}.actions button{min-height:38px;padding:8px 12px;border:1px solid #d5dfed;border-radius:9px;background:#fff;color:#244c7b;font-size:12px;font-weight:700;cursor:pointer}.actions .primary{border-color:#286be4;background:#286be4;color:#fff}.actions button:disabled{opacity:.5;cursor:not-allowed}
    .status{min-height:18px;margin:12px 0 0;color:#52657e;font-size:12px;line-height:1.4}.status[data-state=error]{color:#b42318}.status[data-state=success]{color:#16794b}
    @media(max-width:480px){.launcher{right:12px;bottom:12px}.panel{right:12px;bottom:68px}}
  `;
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "launcher";
  launcher.textContent = "✦ Preparar candidatura";
  launcher.setAttribute("aria-expanded", "false");
  const panel = document.createElement("section");
  panel.className = "panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Preparar candidatura com a Candidatura Certa");
  const heading = document.createElement("h2");
  heading.className = "heading";
  heading.textContent = "Copiloto Candidatura Certa";
  const copy = document.createElement("p");
  copy.className = "copy";
  copy.textContent = `Página: ${location.hostname}. Os campos reconhecidos e vazios serão preenchidos com seu perfil. A revisão e o envio continuam com você.`;
  const consentLabel = document.createElement("label");
  consentLabel.className = "consent";
  const consent = document.createElement("input");
  consent.type = "checkbox";
  const consentText = document.createElement("span");
  consentText.textContent = "Confirmei que este portal permite o preenchimento assistido e autorizo usar meu perfil nesta página.";
  consentLabel.append(consent, consentText);
  const actions = document.createElement("div");
  actions.className = "actions";
  const prepare = document.createElement("button");
  prepare.type = "button";
  prepare.className = "primary";
  prepare.textContent = "Preencher campos compatíveis";
  prepare.disabled = true;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Fechar";
  actions.append(prepare, close);
  const status = document.createElement("p");
  status.className = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.textContent = "Este botão só preenche campos. PDFs e envio são ações separadas, sempre iniciadas por você.";
  panel.append(heading, copy, consentLabel, actions, status);
  shadow.append(style, launcher, panel);
  document.body.append(host);

  function setStatus(text, state = "") {
    status.textContent = text;
    status.dataset.state = state;
  }

  launcher.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    launcher.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) consent.focus();
  });
  close.addEventListener("click", () => {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  });
  consent.addEventListener("change", () => { prepare.disabled = !consent.checked; });
  prepare.addEventListener("click", async () => {
    if (!consent.checked) return;
    prepare.disabled = true;
    consent.disabled = true;
    setStatus("Buscando seu perfil e verificando o limite do plano…");
    const requestId = crypto.randomUUID();
    try {
      const prepared = await chrome.runtime.sendMessage({ type: "CC_PREPARE_PROFILE", requestId, portalAllowed: true });
      if (!prepared?.ok) throw new Error(prepared?.message || "Não foi possível carregar seu perfil.");
      const filler = globalThis.CandidaturaCertaFieldFiller;
      if (!filler?.fillProfileFields) throw new Error("Reabra o copiloto pelo ícone da extensão e tente novamente.");
      const result = filler.fillProfileFields(prepared.value.profile);
      const completion = await chrome.runtime.sendMessage({
        type: "CC_COMPLETE_PREPARATION",
        requestId: prepared.value.request_id,
        filledCount: result?.filled || 0,
      });
      if (!result?.ok) throw new Error(result?.message || "Não foi possível preencher esta página.");
      const usage = prepared.value.usage;
      const quota = `Uso neste mês: ${usage.used}/${usage.limit}.`;
      if (result.filled) {
        setStatus(`${result.filled} campo(s) reconhecido(s) e vazio(s) preenchido(s). ${quota} Revise cada resposta e envie pelo portal.`, "success");
      } else {
        setStatus(`Nenhum campo compatível e vazio foi encontrado. Nada foi alterado. ${quota}`, "");
      }
      if (completion && !completion.ok) setStatus("Os campos foram preenchidos, mas o histórico de uso não foi atualizado. Revise no portal e tente novamente mais tarde.", "error");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Não foi possível preparar esta candidatura.", "error");
    } finally {
      consent.checked = false;
      consent.disabled = false;
      prepare.disabled = true;
    }
  });
  }

  function syncWidget() {
    const shouldShow = !globalThis.__ccCopilotWidgetDismissed
      && pagePolicy.isLikelyJobPage(location.href, () => document.body?.innerText || "");
    if (shouldShow) {
      mountWidget();
    } else if (globalThis.__ccCopilotWidgetInstalled) {
      document.getElementById("cc-copilot-widget-host")?.remove();
      globalThis.__ccCopilotWidgetInstalled = false;
    }
  }

  function scheduleSync() {
    clearTimeout(pendingCheck);
    pendingCheck = setTimeout(syncWidget, 180);
  }

  observer = new MutationObserver(scheduleSync);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  window.addEventListener("popstate", scheduleSync);
  window.addEventListener("hashchange", scheduleSync);
  globalThis.__ccCopilotWidgetDispose = () => {
    observer?.disconnect();
    clearTimeout(pendingCheck);
    window.removeEventListener("popstate", scheduleSync);
    window.removeEventListener("hashchange", scheduleSync);
    document.getElementById("cc-copilot-widget-host")?.remove();
    globalThis.__ccCopilotWidgetInstalled = false;
    delete globalThis.__ccCopilotWidgetDispose;
  };
  scheduleSync();
})();
