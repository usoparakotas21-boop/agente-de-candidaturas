(() => {
  const PROFILE_KEY = "ccAutofillProfileV1";
  const MAX_FILE_BYTES = 1_000_000;
  const automationPolicy = globalThis.CandidaturaCertaAutomationPolicy;
  const $ = id => document.getElementById(id);
  const state = $("profileState");
  const fillButton = $("fillButton");
  const clearButton = $("clearButton");
  const consent = $("pageConsent");
  const attachButton = $("attachPdfsButton");
  const attachmentConsent = $("attachmentConsent");
  const MAX_ATTACHMENT_BYTES = 7 * 1024 * 1024;
  let savedProfile = null;
  let activePageUrl = "";
  const fieldLabels = {
    name: "nome", first_name: "primeiro nome", last_name: "sobrenome", email: "e-mail", phone: "telefone",
    linkedin: "LinkedIn", website: "site/portfólio", location: "localização", city: "cidade", state: "estado",
    headline: "título profissional", summary: "resumo", experiences: "experiência", education: "formação",
    skills: "competências", languages: "idiomas"
  };

  function message(text, type = "") {
    const target = $("pageState");
    target.textContent = text;
    target.dataset.state = type;
  }

  function clean(value, max = 12_000) {
    return typeof value === "string" ? value.trim().slice(0, max) : "";
  }

  function normalizeProfile(raw) {
    if (!raw || raw.schema_version !== 1 || !raw.profile || typeof raw.profile !== "object") {
      throw new Error("Arquivo inválido. Exporte o perfil pela página Perfil da Candidatura Certa.");
    }
    const source = raw.profile;
    const profile = {
      name: clean(source.name, 180), email: clean(source.email, 240), phone: clean(source.phone, 80),
      linkedin: clean(source.linkedin, 500), website: clean(source.website, 500), location: clean(source.location, 180),
      headline: clean(source.headline, 500), summary: clean(source.summary, 5000),
      experiences: Array.isArray(source.experiences) ? source.experiences.slice(0, 50).map(item => ({
        role: clean(item?.role, 200), company: clean(item?.company, 200), period: clean(item?.period, 100), description: clean(item?.description, 5000)
      })) : [],
      education: Array.isArray(source.education) ? source.education.slice(0, 50).map(item => ({
        course: clean(item?.course, 200), institution: clean(item?.institution, 200), period: clean(item?.period, 100)
      })) : [],
      skills: Array.isArray(source.skills) ? source.skills.slice(0, 100).map(item => clean(item, 200)).filter(Boolean) : [],
      languages: Array.isArray(source.languages) ? source.languages.slice(0, 30).map(item => clean(item, 100)).filter(Boolean) : []
    };
    if (!profile.name && !profile.email && !profile.phone) throw new Error("O arquivo não contém dados básicos do perfil.");
    return profile;
  }

  function updateProfileState(profile) {
    savedProfile = profile || null;
    state.textContent = profile ? (profile.name || profile.email || "Perfil importado") : "Nenhum perfil importado";
    const restricted = isActivePageRestricted();
    consent.disabled = restricted;
    fillButton.disabled = !profile || !consent.checked || restricted;
    clearButton.disabled = !profile;
    updateAttachmentControls();
    if (restricted) message(restrictedPageMessage(), "error");
  }

  function updateAttachmentControls() {
    const resume = $("resumePdf").files?.[0];
    const letter = $("letterPdf").files?.[0];
    const selectedSize = (resume?.size || 0) + (letter?.size || 0);
    const restricted = isActivePageRestricted();
    attachButton.disabled = !resume || !attachmentConsent.checked || selectedSize > MAX_ATTACHMENT_BYTES || restricted;
    if (selectedSize > MAX_ATTACHMENT_BYTES) {
      $("attachmentState").textContent = "Os PDFs selecionados passam do limite combinado de 7 MB.";
      $("attachmentState").dataset.state = "error";
    } else if ($("attachmentState").dataset.state === "error") {
      $("attachmentState").textContent = "";
      $("attachmentState").dataset.state = "";
    }
  }

  function readPdf(file) {
    if (!file || !/\.pdf$/i.test(file.name)) {
      throw new Error("Selecione arquivos PDF válidos para currículo e carta.");
    }
    if (file.size > MAX_ATTACHMENT_BYTES) throw new Error("Cada envio aceita até 7 MB no total.");
    return file.arrayBuffer().then(buffer => {
      const bytes = new Uint8Array(buffer);
      if (bytes.length < 5 || new TextDecoder().decode(bytes.subarray(0, 5)) !== "%PDF-") {
        throw new Error("O arquivo selecionado não tem a assinatura de um PDF válido.");
      }
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
      }
      return {
        name: file.name.replace(/[^A-Za-z0-9._-]/g, "-").slice(-120) || "documento.pdf",
        base64: btoa(binary),
      };
    });
  }

  function restrictedPageMessage(url = activePageUrl) {
    try {
      return automationPolicy.restrictedMessageFor(new URL(url).hostname);
    } catch {
      return "Este portal restringe automação de terceiros. Nada foi acessado ou preenchido.";
    }
  }

  function isActivePageRestricted(url = activePageUrl) {
    try {
      return automationPolicy.isRestrictedAutomationHost(new URL(url).hostname);
    } catch {
      return false;
    }
  }

  async function loadProfile() {
    const stored = await chrome.storage.local.get(PROFILE_KEY);
    if (!stored[PROFILE_KEY]) return updateProfileState(null);
    try { updateProfileState(normalizeProfile(stored[PROFILE_KEY])); }
    catch { await chrome.storage.local.remove(PROFILE_KEY); updateProfileState(null); }
  }

  chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
    let host = "Página indisponível";
    activePageUrl = tab?.url || "";
    try { host = new URL(activePageUrl).hostname || host; } catch { /* páginas internas não têm host HTTPS */ }
    $("activePage").textContent = `Página ativa: ${host}`;
    updateProfileState(savedProfile);
  }).catch(() => { $("activePage").textContent = "Não foi possível identificar a página ativa."; });

  $("profileFile").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) return message("O arquivo passa do limite de 1 MB.", "error");
    try {
      const parsed = JSON.parse(await file.text());
      const profile = normalizeProfile(parsed);
      await chrome.storage.local.set({ [PROFILE_KEY]: { schema_version: 1, profile } });
      consent.checked = false;
      updateProfileState(profile);
      message("Perfil importado somente neste Chrome. Marque a autorização para preencher uma página.", "success");
    } catch (error) {
      message(error instanceof Error ? error.message : "Não foi possível ler o arquivo.", "error");
    }
  });

  consent.addEventListener("change", () => { fillButton.disabled = !savedProfile || !consent.checked || isActivePageRestricted(); });

  [$("resumePdf"), $("letterPdf")].forEach(input => input.addEventListener("change", () => {
    if ($("attachmentState").dataset.state === "success") {
      $("attachmentState").textContent = "";
      $("attachmentState").dataset.state = "";
    }
    updateAttachmentControls();
  }));
  attachmentConsent.addEventListener("change", updateAttachmentControls);

  attachButton.addEventListener("click", async () => {
    if (isActivePageRestricted()) {
      $("attachmentState").textContent = restrictedPageMessage();
      $("attachmentState").dataset.state = "error";
      return;
    }
    if (!attachmentConsent.checked) return;
    attachButton.disabled = true;
    $("attachmentState").textContent = "Verificando os campos de arquivo desta aba…";
    $("attachmentState").dataset.state = "";
    try {
      const resume = $("resumePdf").files?.[0];
      const letter = $("letterPdf").files?.[0];
      if (!resume) throw new Error("Escolha o currículo em PDF que deseja anexar.");
      const totalSize = (resume?.size || 0) + (letter?.size || 0);
      if (totalSize > MAX_ATTACHMENT_BYTES) throw new Error("Os PDFs selecionados passam do limite combinado de 7 MB.");
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id || !/^https:\/\//i.test(tab.url || "")) throw new Error("Abra o formulário HTTPS da vaga e tente novamente.");
      if (isActivePageRestricted(tab.url)) throw new Error(restrictedPageMessage(tab.url));
      const files = {
        resume: await readPdf(resume),
        letter: letter ? await readPdf(letter) : null,
      };
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: globalThis.CandidaturaCertaPdfAttachment.attachPdfsInPage,
        args: [files],
      });
      if (!result?.result?.ok) throw new Error(result?.result?.message || "Nenhum campo de upload claramente identificado foi alterado.");
      $("attachmentState").textContent = result.result.message;
      $("attachmentState").dataset.state = "success";
      $("resumePdf").value = "";
      $("letterPdf").value = "";
      attachmentConsent.checked = false;
    } catch (error) {
      $("attachmentState").textContent = error instanceof Error ? error.message : "Não foi possível anexar os PDFs nesta página.";
      $("attachmentState").dataset.state = "error";
    } finally {
      updateAttachmentControls();
    }
  });

  fillButton.addEventListener("click", async () => {
    if (isActivePageRestricted()) {
      message(restrictedPageMessage(), "error");
      return;
    }
    if (!savedProfile || !consent.checked) return;
    fillButton.disabled = true;
    message("Analisando apenas os campos visíveis desta aba…");
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id || !/^https:\/\//i.test(tab.url || "")) throw new Error("Abra um formulário seguro em uma página HTTPS e tente novamente.");
      if (isActivePageRestricted(tab.url)) throw new Error(restrictedPageMessage(tab.url));
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["field-filler.js"] });
      const result = await chrome.tabs.sendMessage(tab.id, { type: "CC_FILL_PROFILE_FIELDS", profile: savedProfile });
      if (!result?.ok) throw new Error(result?.message || "Não foi possível preencher esta página.");
      const labels = [...new Set((result.filledKeys || []).map(key => fieldLabels[key]).filter(Boolean))];
      const summary = labels.length ? ` Campos: ${labels.join(", ")}.` : "";
      message(result.filled ? `${result.filled} campo(s) em branco preenchido(s).${summary} Confira cada resposta e envie pelo portal.` : "Nenhum campo compatível e vazio foi encontrado. Nada foi enviado.", result.filled ? "success" : "");
    } catch (error) {
      message(error instanceof Error ? error.message : "O Chrome bloqueou o preenchimento desta página.", "error");
    } finally {
      fillButton.disabled = !savedProfile || !consent.checked || isActivePageRestricted();
    }
  });

  clearButton.addEventListener("click", async () => {
    await chrome.storage.local.remove(PROFILE_KEY);
    consent.checked = false;
    updateProfileState(null);
    message("Perfil removido do armazenamento local do complemento.", "success");
  });

  loadProfile().catch(() => message("Não foi possível acessar o armazenamento deste Chrome.", "error"));
})();
