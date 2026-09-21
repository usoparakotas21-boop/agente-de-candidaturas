(() => {
  const APP_ORIGINS = [
    "https://candidaturacerta.com.br",
    "https://agente-de-candidaturas.onrender.com",
  ];
  const MAX_ATTACHMENT_BYTES = 7 * 1024 * 1024;
  const $ = id => document.getElementById(id);
  const accountState = $("accountState");
  const connectButton = $("connectButton");
  const copyPanelButton = $("copyPanelButton");
  const portalConsent = $("portalConsent");
  const showWidgetButton = $("showWidgetButton");
  const autoWidgetButton = $("autoWidgetButton");
  const closeWidgetButton = $("closeWidgetButton");
  const attachButton = $("attachPdfsButton");
  const attachmentConsent = $("attachmentConsent");
  const loadLibraryButton = $("loadLibraryDocuments");
  const libraryApplication = $("libraryApplication");
  const libraryConsent = $("libraryAttachmentConsent");
  const attachLibraryButton = $("attachLibraryDocuments");
  let activeTab = null;
  let connected = false;
  let activePageUrl = "";
  let libraryItems = [];

  function setMessage(element, message, state = "") {
    element.textContent = message;
    element.dataset.state = state;
  }

  function sitePermission() {
    return { permissions: ["cookies"], origins: APP_ORIGINS.map(origin => `${origin}/*`) };
  }

  function hostIsSupported(url = activePageUrl) {
    try {
      const parsed = new URL(url);
      return parsed.protocol === "https:" && globalThis.CandidaturaCertaAutomationPolicy.isSupportedAutomationHost(parsed.hostname);
    } catch {
      return false;
    }
  }

  function updatePageControls() {
    const supported = hostIsSupported();
    const checked = Boolean(portalConsent.checked);
    showWidgetButton.disabled = !connected || !supported || !checked || !activeTab?.id;
    autoWidgetButton.disabled = !supported || !activeTab?.id || (!connected && autoWidgetButton.dataset.enabled !== "true");
    closeWidgetButton.disabled = !supported || !activeTab?.id;
    updateLibraryControls();
    if (!supported) {
      let host = "página indisponível";
      try { host = new URL(activePageUrl).hostname; } catch { /* página sem URL web */ }
      $("activePage").textContent = `Página ativa: ${host}. O copiloto está disponível em Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br.`;
      if (globalThis.CandidaturaCertaAutomationPolicy.isRestrictedAutomationHost(host)) {
        setMessage($("pageState"), globalThis.CandidaturaCertaAutomationPolicy.restrictedMessageFor(host), "error");
      }
    }
  }

  function updateLibraryControls() {
    const supported = hostIsSupported() && Boolean(activeTab?.id);
    loadLibraryButton.disabled = !connected || !supported;
    libraryApplication.disabled = !connected || !supported || !libraryItems.length;
    attachLibraryButton.disabled = !connected || !supported || !libraryApplication.value || !libraryConsent.checked;
  }

  async function getPermission() {
    return chrome.permissions.contains(sitePermission());
  }

  async function refreshAccountStatus() {
    connected = false;
    copyPanelButton.disabled = true;
    updateLibraryControls();
    if (!(await getPermission())) {
      connectButton.textContent = "Conectar minha conta";
      setMessage(accountState, "Conecte sua conta para consultar seu perfil e o limite do plano.");
      updatePageControls();
      return;
    }
    setMessage(accountState, "Verificando sua sessão…");
    const result = await chrome.runtime.sendMessage({ type: "CC_GET_STATUS" });
    if (!result?.ok) {
      connectButton.textContent = "Reconectar minha conta";
      setMessage(accountState, result?.message || "Sua sessão não está disponível. Entre no site e tente novamente.", "error");
      updatePageControls();
      return;
    }
    connected = true;
    const usage = result.value;
    const plan = { essential: "Essencial", start: "Start", pro: "Pro", consultoria: "Consultoria" }[usage.plan_code] || "Essencial";
    setMessage(accountState, `Conectado · ${plan} · preparações neste mês: ${usage.used}/${usage.limit}. Renova em ${new Date(usage.resets_at).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" })}.`, "success");
    connectButton.textContent = "Desconectar";
    copyPanelButton.disabled = false;
    updatePageControls();
  }

  async function refreshAutoWidgetStatus() {
    autoWidgetButton.dataset.enabled = "false";
    autoWidgetButton.textContent = "Ativar botão automaticamente neste domínio";
    if (!activeTab?.id || !hostIsSupported()) return;
    const result = await chrome.runtime.sendMessage({ type: "CC_GET_AUTO_WIDGET_STATUS", tabId: activeTab.id });
    if (!result?.ok) return;
    const enabled = Boolean(result.value?.enabled);
    autoWidgetButton.dataset.enabled = String(enabled);
    autoWidgetButton.textContent = enabled
      ? `Desativar botão automático em ${result.value.host}`
      : "Ativar botão automaticamente neste domínio";
    updatePageControls();
  }

  connectButton.addEventListener("click", async () => {
    connectButton.disabled = true;
    try {
      if (connected) {
        await chrome.permissions.remove(sitePermission());
        connected = false;
        setMessage(accountState, "Complemento desconectado. Nenhum token fica guardado nele.", "success");
        connectButton.textContent = "Conectar minha conta";
        copyPanelButton.disabled = true;
        updatePageControls();
        await refreshAutoWidgetStatus();
      } else {
        // This permission prompt is intentionally opened only by this click.
        const granted = await chrome.permissions.request(sitePermission());
        if (!granted) throw new Error("A permissão não foi concedida. Você pode continuar usando o site sem conectar o complemento.");
        await refreshAccountStatus();
        await refreshAutoWidgetStatus();
      }
    } catch (error) {
      setMessage(accountState, error instanceof Error ? error.message : "Não foi possível conectar a conta.", "error");
    } finally {
      connectButton.disabled = false;
    }
  });

  copyPanelButton.addEventListener("click", async () => {
    if (!connected || !activeTab?.id) return;
    try {
      await chrome.sidePanel.open({ tabId: activeTab.id });
    } catch {
      setMessage(accountState, "Não foi possível abrir o painel. Atualize o Chrome e tente novamente.", "error");
    }
  });

  portalConsent.addEventListener("change", updatePageControls);
  showWidgetButton.addEventListener("click", async () => {
    showWidgetButton.disabled = true;
    try {
      if (!activeTab?.id || !hostIsSupported()) throw new Error("Abra uma página HTTPS de vaga em um portal compatível.");
      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        func: () => { globalThis.__ccCopilotWidgetDismissed = false; },
      });
      await chrome.scripting.executeScript({ target: { tabId: activeTab.id }, files: ["job-page-policy.js", "job-context.js", "portal-selectors.js", "field-filler.js", "copilot-widget.js"] });
      setMessage($("pageState"), "Botão adicionado nesta página. Clique nele, confirme o uso do seu perfil e revise antes de enviar.", "success");
      portalConsent.checked = false;
    } catch (error) {
      setMessage($("pageState"), error instanceof Error ? error.message : "O Chrome não permitiu adicionar o botão nesta página.", "error");
    } finally {
      updatePageControls();
    }
  });

  autoWidgetButton.addEventListener("click", async () => {
    autoWidgetButton.disabled = true;
    try {
      if (!activeTab?.id || !hostIsSupported()) throw new Error("Abra uma página HTTPS de vaga em um portal compatível.");
      const page = new URL(activePageUrl);
      const enabled = autoWidgetButton.dataset.enabled === "true";
      if (enabled) {
        const result = await chrome.runtime.sendMessage({ type: "CC_DISABLE_AUTO_WIDGET", tabId: activeTab.id });
        if (!result?.ok) throw new Error(result?.message || "Não foi possível desativar o botão neste domínio.");
        await chrome.permissions.remove({ origins: [`${page.origin}/*`] });
        portalConsent.checked = false;
        setMessage($("pageState"), `Botão automático desativado em ${page.hostname}; a permissão do domínio foi removida.`, "success");
      } else {
        if (!connected) throw new Error("Conecte sua conta antes de ativar o botão automático.");
        if (!portalConsent.checked) throw new Error("Confirme primeiro que este portal permite preenchimento assistido.");
        const granted = await chrome.permissions.request({ origins: [`${page.origin}/*`] });
        if (!granted) throw new Error("A permissão não foi concedida. Nada foi instalado neste domínio.");
        const result = await chrome.runtime.sendMessage({ type: "CC_ENABLE_AUTO_WIDGET", tabId: activeTab.id });
        if (!result?.ok) {
          await chrome.permissions.remove({ origins: [`${page.origin}/*`] });
          throw new Error(result?.message || "Não foi possível ativar o botão automático.");
        }
        portalConsent.checked = false;
        setMessage($("pageState"), `Pronto: o botão aparecerá nas páginas de vagas reconhecidas em ${page.hostname}. Ele só acessa seu perfil após seu clique e autorização.`, "success");
      }
      await refreshAutoWidgetStatus();
    } catch (error) {
      setMessage($("pageState"), error instanceof Error ? error.message : "Não foi possível alterar a ativação automática.", "error");
    } finally {
      updatePageControls();
    }
  });

  closeWidgetButton.addEventListener("click", async () => {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
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
      setMessage($("pageState"), "Botão removido desta página.", "success");
    } catch {
      setMessage($("pageState"), "Não há um botão ativo nesta página ou ela foi fechada.");
    }
  });

  function readPdf(file) {
    if (!file || !/\.pdf$/i.test(file.name)) throw new Error("Selecione arquivos PDF válidos para currículo e carta.");
    if (file.size > MAX_ATTACHMENT_BYTES) throw new Error("O tamanho combinado dos PDFs não pode passar de 7 MB.");
    return file.arrayBuffer().then(buffer => {
      const bytes = new Uint8Array(buffer);
      if (bytes.length < 5 || new TextDecoder().decode(bytes.subarray(0, 5)) !== "%PDF-") throw new Error("O arquivo selecionado não parece ser um PDF válido.");
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
      return { name: file.name.replace(/[^A-Za-z0-9._-]/g, "-").slice(-120) || "documento.pdf", base64: btoa(binary) };
    });
  }

  async function attachFilesOnActivePage(files) {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: globalThis.CandidaturaCertaPdfAttachment.attachPdfsInPage,
      args: [files],
    });
    if (!result?.result?.ok) throw new Error(result?.result?.message || "Nenhum campo de anexo de currículo ou carta foi identificado com segurança.");
    return result.result.message;
  }

  function updateAttachmentControls() {
    const resume = $("resumePdf").files?.[0];
    const letter = $("letterPdf").files?.[0];
    const total = (resume?.size || 0) + (letter?.size || 0);
    attachButton.disabled = !resume || !attachmentConsent.checked || total > MAX_ATTACHMENT_BYTES || !hostIsSupported();
    if (total > MAX_ATTACHMENT_BYTES) setMessage($("attachmentState"), "Os PDFs selecionados passam do limite combinado de 7 MB.", "error");
  }

  [$("resumePdf"), $("letterPdf")].forEach(input => input.addEventListener("change", updateAttachmentControls));
  attachmentConsent.addEventListener("change", updateAttachmentControls);
  attachButton.addEventListener("click", async () => {
    attachButton.disabled = true;
    try {
      if (!attachmentConsent.checked || !hostIsSupported()) throw new Error("Confirme que este portal permite anexação assistida.");
      const resume = $("resumePdf").files?.[0];
      const letter = $("letterPdf").files?.[0];
      const total = (resume?.size || 0) + (letter?.size || 0);
      if (total > MAX_ATTACHMENT_BYTES) throw new Error("Os PDFs selecionados passam do limite combinado de 7 MB.");
      const files = { resume: await readPdf(resume), letter: letter ? await readPdf(letter) : null };
      const message = await attachFilesOnActivePage(files);
      setMessage($("attachmentState"), message, "success");
      $("resumePdf").value = "";
      $("letterPdf").value = "";
      attachmentConsent.checked = false;
    } catch (error) {
      setMessage($("attachmentState"), error instanceof Error ? error.message : "Não foi possível anexar os PDFs nesta página.", "error");
    } finally {
      updateAttachmentControls();
    }
  });

  loadLibraryButton.addEventListener("click", async () => {
    loadLibraryButton.disabled = true;
    setMessage($("libraryState"), "Buscando seus documentos salvos…");
    try {
      const response = await chrome.runtime.sendMessage({ type: "CC_LIST_DOCUMENTS" });
      if (!response?.ok) throw new Error(response?.message || "Não foi possível carregar sua biblioteca.");
      libraryItems = Array.isArray(response.value?.items) ? response.value.items : [];
      libraryApplication.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = libraryItems.length ? "Selecione a vaga" : "Nenhum par de documentos disponível";
      libraryApplication.append(placeholder);
      for (const item of libraryItems) {
        const option = document.createElement("option");
        option.value = String(item.application_id);
        option.textContent = `${item.title || "Oportunidade"} · ${item.company || "Empresa não informada"}`;
        libraryApplication.append(option);
      }
      setMessage($("libraryState"), libraryItems.length
        ? `${libraryItems.length} candidatura(s) com currículo e carta atuais disponíveis.`
        : "Gere e salve o currículo e a carta de uma vaga no site; depois eles aparecerão aqui.");
      libraryConsent.checked = false;
      updateLibraryControls();
    } catch (error) {
      setMessage($("libraryState"), error instanceof Error ? error.message : "Não foi possível carregar sua biblioteca.", "error");
    } finally {
      updateLibraryControls();
    }
  });

  libraryApplication.addEventListener("change", updateLibraryControls);
  libraryConsent.addEventListener("change", updateLibraryControls);
  attachLibraryButton.addEventListener("click", async () => {
    attachLibraryButton.disabled = true;
    try {
      const applicationId = Number(libraryApplication.value);
      if (!connected || !libraryConsent.checked || !hostIsSupported() || !Number.isSafeInteger(applicationId) || applicationId < 1) {
        throw new Error("Selecione uma vaga salva, confirme o uso dos PDFs e abra um portal compatível.");
      }
      setMessage($("libraryState"), "Buscando os PDFs atuais e procurando campos identificados…");
      const response = await chrome.runtime.sendMessage({
        type: "CC_GET_APPLICATION_PDFS",
        applicationId,
        tabId: activeTab.id,
      });
      if (!response?.ok) throw new Error(response?.message || "Não foi possível buscar os documentos atuais.");
      const message = await attachFilesOnActivePage({
        resume: response.value.resume,
        letter: response.value.letter,
      });
      setMessage($("libraryState"), message, "success");
      libraryConsent.checked = false;
    } catch (error) {
      setMessage($("libraryState"), error instanceof Error ? error.message : "Não foi possível anexar os PDFs da biblioteca.", "error");
    } finally {
      updateLibraryControls();
    }
  });

  chrome.tabs.query({ active: true, currentWindow: true }).then(async ([tab]) => {
    activeTab = tab || null;
    activePageUrl = tab?.url || "";
    let host = "página indisponível";
    try { host = new URL(activePageUrl).hostname; } catch { /* página interna */ }
    $("activePage").textContent = `Página ativa: ${host}`;
    updatePageControls();
    updateAttachmentControls();
    try { await refreshAccountStatus(); }
    catch (error) { setMessage(accountState, error instanceof Error ? error.message : "Conecte sua conta para continuar."); }
    try { await refreshAutoWidgetStatus(); } catch { /* a página pode não ser um portal compatível */ }
  }).catch(() => setMessage($("activePage"), "Não foi possível identificar a página ativa.", "error"));
})();
