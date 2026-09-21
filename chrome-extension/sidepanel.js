(() => {
  const loadButton = document.getElementById("loadProfile");
  const status = document.getElementById("status");
  const items = document.getElementById("items");

  function setStatus(message, state = "") {
    status.textContent = message;
    status.dataset.state = state;
  }

  function addSnippet(label, value) {
    const text = String(value || "").trim();
    if (!text) return;
    const card = document.createElement("section");
    card.className = "item";
    const head = document.createElement("div");
    head.className = "item-head";
    const title = document.createElement("h2");
    title.textContent = label;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Copiar";
    const preview = document.createElement("p");
    preview.className = "value";
    preview.textContent = text;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        setStatus(`${label} copiado. Cole no campo correspondente e revise.`, "success");
      } catch {
        setStatus("O navegador não liberou a área de transferência. Selecione o texto e copie manualmente.", "error");
      }
    });
    head.append(title, button);
    card.append(head, preview);
    items.append(card);
  }

  loadButton.addEventListener("click", async () => {
    loadButton.disabled = true;
    items.replaceChildren();
    setStatus("Buscando os dados do seu perfil…");
    try {
      const response = await chrome.runtime.sendMessage({ type: "CC_GET_PROFILE" });
      if (!response?.ok) throw new Error(response?.message || "Não foi possível carregar seu perfil.");
      const { profile, usage } = response.value;
      addSnippet("Nome", profile.name);
      addSnippet("E-mail", profile.email);
      addSnippet("Telefone", profile.phone);
      addSnippet("Localização", profile.location);
      addSnippet("Título profissional", profile.headline);
      addSnippet("Resumo profissional", profile.summary);
      (profile.experiences || []).forEach((item, index) => addSnippet(
        `Experiência ${index + 1}`,
        [item.role, item.company, item.period, item.description].filter(Boolean).join(" — "),
      ));
      if (Array.isArray(profile.education) && profile.education.length) {
        addSnippet("Formação", profile.education.map(item => [item.course, item.institution, item.period].filter(Boolean).join(" — ")).join("\n"));
      }
      addSnippet("Competências", (profile.skills || []).join(", "));
      addSnippet("Idiomas", (profile.languages || []).join(", "));
      if (!items.childElementCount) throw new Error("Seu perfil não tem dados para copiar. Complete-o no site e tente novamente.");
      setStatus(`Perfil carregado somente neste painel. Uso deste mês: ${usage.used}/${usage.limit}.`, "success");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Não foi possível carregar os dados.", "error");
    } finally {
      loadButton.disabled = false;
    }
  });
})();
