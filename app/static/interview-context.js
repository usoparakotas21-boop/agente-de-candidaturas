(() => {
  const select = document.querySelector("#applicationSelect");
  const loadButton = document.querySelector("#loadPrep");
  const retryButton = document.querySelector("#retryApplications");
  const status = document.querySelector("#prepStatus");
  const summary = document.querySelector("#prepSummary");
  const questions = Array.from(document.querySelectorAll(".question"));
  if (!select || !loadButton || !retryButton || !status || !summary || !questions.length) return;

  const defaults = questions.map(question => ({
    title: question.querySelector("h2")?.textContent || "",
    prompt: question.querySelector("p")?.textContent || "",
    label: question.dataset.title || "pergunta",
  }));

  const setStatus = (message, isError = false) => {
    status.textContent = message;
    status.classList.toggle("error", isError);
  };

  const restoreDefaultQuestions = () => {
    window.interviewPrepContext = "";
    questions.forEach((question, index) => {
      const title = question.querySelector("h2");
      const prompt = question.querySelector("p");
      if (title) title.textContent = defaults[index].title;
      if (prompt) prompt.textContent = defaults[index].prompt;
      question.dataset.title = defaults[index].label;
    });
    summary.hidden = true;
    summary.textContent = "";
  };

  const loadApplications = async () => {
    retryButton.hidden = true;
    try {
      const response = await fetch("/applications", {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error();
      const data = await response.json();
      const applications = Array.isArray(data.applications) ? data.applications : [];
      select.replaceChildren(new Option("Escolha uma candidatura", ""));
      applications.forEach(application => {
        const title = String(application.job_title || "Vaga sem título").trim();
        const company = String(application.company || "").trim();
        const label = company ? `${title} — ${company}` : title;
        select.add(new Option(label, String(application.id)));
      });
      if (!applications.length) {
        setStatus("Ainda não há candidaturas para vincular. Você pode praticar com as perguntas gerais.");
      } else {
        setStatus("Opcional: escolha uma candidatura para adaptar as perguntas aos pontos da vaga.");
      }
    } catch (_) {
      select.replaceChildren(new Option("Não foi possível carregar as candidaturas", ""));
      setStatus("Não foi possível carregar suas candidaturas agora. Tente novamente mais tarde; a simulação geral continua disponível.", true);
      retryButton.hidden = false;
    }
  };

  retryButton.addEventListener("click", () => void loadApplications());

  select.addEventListener("change", () => {
    restoreDefaultQuestions();
    loadButton.disabled = !select.value;
    window.dispatchEvent(new CustomEvent("interview:context-reset"));
    if (select.value) setStatus("A avaliação foi reiniciada para esta candidatura. As respostas digitadas foram mantidas; carregue o roteiro personalizado quando quiser.");
    else setStatus("A simulação geral continua disponível. Selecione uma candidatura para personalizar as perguntas.");
  });

  loadButton.addEventListener("click", async () => {
    const applicationId = select.value;
    if (!applicationId) return;
    loadButton.disabled = true;
    loadButton.textContent = "Carregando roteiro…";
    restoreDefaultQuestions();
    setStatus("Buscando pontos fortes e perguntas desta candidatura…");
    try {
      const response = await fetch(`/api/interviews/prep/${encodeURIComponent(applicationId)}`, {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error();
      const prep = await response.json();
      const personalized = Array.isArray(prep.questions) ? prep.questions.filter(item => typeof item === "string" && item.trim()).slice(0, questions.length) : [];
      if (!personalized.length) throw new Error();
      personalized.forEach((text, index) => {
        const question = questions[index];
        const title = question.querySelector("h2");
        const prompt = question.querySelector("p");
        if (title) title.textContent = text;
        if (prompt) prompt.textContent = prep.answer_framework || "Responda com uma experiência real e explique contexto, ação e resultado.";
        question.dataset.title = `vaga ${index + 1}`;
      });
      const details = [
        `Roteiro: ${prep.job_title || "candidatura selecionada"}${prep.company ? ` — ${prep.company}` : ""}.`,
        prep.strengths?.length ? `Pontos fortes: ${prep.strengths.join(" · ")}.` : "",
        prep.gaps?.length ? `Pontos para preparar: ${prep.gaps.join(" · ")}.` : "",
      ].filter(Boolean);
      summary.textContent = details.join(" ");
      window.interviewPrepContext = details.join(" ");
      summary.hidden = false;
      setStatus("Perguntas personalizadas carregadas. O restante da simulação continua com perguntas gerais.");
    } catch (_) {
      setStatus("Não foi possível montar o roteiro desta candidatura. Confira se ela ainda está disponível e tente novamente.", true);
    } finally {
      loadButton.disabled = !select.value;
      loadButton.textContent = "Carregar perguntas da vaga";
    }
  });

  void loadApplications();
})();
