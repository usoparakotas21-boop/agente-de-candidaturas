(() => {
  const loadButton = document.getElementById("loadProfile");
  const status = document.getElementById("status");
  const items = document.getElementById("items");
  const analyzeButton = document.getElementById("analyzeJob");
  const analysisConsent = document.getElementById("analysisConsent");
  const geminiConsent = document.getElementById("geminiConsent");
  const jobStatus = document.getElementById("jobStatus");
  const jobItems = document.getElementById("jobItems");

  function setStatus(message, state = "") {
    status.textContent = message;
    status.dataset.state = state;
  }

  function addSnippet(label, value, target = items) {
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
    target.append(card);
  }

  function setJobStatus(message, state = "") {
    jobStatus.textContent = message;
    jobStatus.dataset.state = state;
  }

  analysisConsent.addEventListener("change", () => { analyzeButton.disabled = !analysisConsent.checked; });
  analyzeButton.addEventListener("click", async () => {
    if (!analysisConsent.checked) return;
    analyzeButton.disabled = true;
    jobItems.replaceChildren();
    setJobStatus("Lendo a vaga visível na aba ativa…");
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) throw new Error("Volte à vaga e abra novamente a cópia rápida.");
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["job-context.js"] });
      const [extracted] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => globalThis.CandidaturaCertaJobContext?.extractVisibleJobContext(document) || null,
      });
      const jobContext = extracted?.result;
      if (!jobContext || !jobContext.description) throw new Error("Não encontrei uma descrição de vaga visível nesta página. Nenhum dado foi enviado.");
      const response = await chrome.runtime.sendMessage({
        type: "CC_ANALYZE_JOB",
        tabId: tab.id,
        requestId: crypto.randomUUID(),
        jobContext,
        consent: true,
        useGemini: geminiConsent.checked,
      });
      if (!response?.ok) throw new Error(response?.message || "Não foi possível analisar esta vaga.");
      const { vacancy, vacancy_analysis: analysis, usage } = response.value;
      if (!analysis) throw new Error("Não foi possível calcular a compatibilidade com os dados encontrados.");
      const contextLabel = [vacancy.title, vacancy.company, vacancy.location].filter(Boolean).join(" · ");
      const geminiMessage = response.value.ai_status === "unavailable"
        ? " Gemini indisponível; exibindo sugestões baseadas no perfil."
        : response.value.ai_status === "ready" ? " Rascunhos do Gemini prontos; confira todos os fatos." : "";
      setJobStatus(`${contextLabel ? `${contextLabel} — ` : ""}${analysis.score}/100 · ${analysis.recommendation}. Uso neste mês: ${usage.used}/${usage.limit}.${geminiMessage}`, "success");
      addSnippet(response.value.ai_status === "ready" ? "Resumo do Gemini — revise antes de usar" : "Resumo sugerido — revise antes de usar", analysis.summary, jobItems);
      if (analysis.ai_suggestions?.talking_points?.length) addSnippet("Pontos de conversa sugeridos pelo Gemini", analysis.ai_suggestions.talking_points.join("\n"), jobItems);
      if (analysis.ai_suggestions?.questions_to_prepare?.length) addSnippet("Perguntas para você preparar", analysis.ai_suggestions.questions_to_prepare.join("\n"), jobItems);
      if (analysis.strengths?.length) addSnippet("Pontos compatíveis do perfil", analysis.strengths.join(", "), jobItems);
      if (analysis.gaps?.length) addSnippet("Requisitos para conferir", analysis.gaps.join(", "), jobItems);
      if (analysis.skills?.length) addSnippet("Competências alinhadas registradas", analysis.skills.join(", "), jobItems);
      for (const experience of analysis.experiences || []) {
        addSnippet(
          [experience.role, experience.company].filter(Boolean).join(" · ") || "Experiência relacionada",
          experience.description,
          jobItems,
        );
      }
      if (!jobItems.childElementCount) setJobStatus("A vaga foi analisada, mas não há sugestões para exibir. Complete seu perfil e tente novamente.", "");
    } catch (error) {
      setJobStatus(error instanceof Error ? error.message : "Não foi possível analisar a vaga.", "error");
    } finally {
      analysisConsent.checked = false;
      geminiConsent.checked = false;
      analyzeButton.disabled = true;
    }
  });

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
