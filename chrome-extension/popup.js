(() => {
  const PROFILE_KEY = "ccAutofillProfileV1";
  const MAX_FILE_BYTES = 1_000_000;
  const automationPolicy = globalThis.CandidaturaCertaAutomationPolicy;
  const $ = id => document.getElementById(id);
  const state = $("profileState");
  const fillButton = $("fillButton");
  const clearButton = $("clearButton");
  const consent = $("pageConsent");
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
    if (restricted) message(restrictedPageMessage(), "error");
  }

  function restrictedPageMessage() {
    try {
      return automationPolicy.restrictedMessageFor(new URL(activePageUrl).hostname);
    } catch {
      return "Este portal restringe automação de terceiros. Nada foi acessado ou preenchido.";
    }
  }

  function isActivePageRestricted() {
    try {
      return automationPolicy.isRestrictedAutomationHost(new URL(activePageUrl).hostname);
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
