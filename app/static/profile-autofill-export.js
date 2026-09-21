(() => {
  const profileForm = document.querySelector("#profileForm");
  const extractedForm = document.querySelector("#extractedForm");
  if (!profileForm || !extractedForm) return;

  const style = document.createElement("style");
  style.textContent = ".cc-assistant-note{margin:12px 0 16px}.cc-assistant-actions{justify-content:flex-start;flex-wrap:wrap}.cc-assistant-status{margin:12px 0 0}";
  document.head.append(style);

  const card = document.createElement("section");
  card.className = "card";
  card.setAttribute("aria-labelledby", "browser-assistant-title");
  card.innerHTML = `
    <h2 id="browser-assistant-title">Candidatura assistida no navegador</h2>
    <p>Preencha campos reconhecidos em formulários de candidatura compatíveis. Você confere tudo e envia no próprio portal.</p>
    <div class="tip cc-assistant-note">O complemento não envia candidaturas, não faz login, não resolve CAPTCHA e não contorna regras do portal. Use somente onde o preenchimento assistido for permitido. Seus dados ficam no perfil local do Chrome e não são enviados pelo complemento.</div>
    <div class="actions cc-assistant-actions">
      <a class="secondary" href="/static/candidatura-certa-autopreenchimento.zip" download>Baixar complemento para Chrome</a>
      <button class="primary" type="button" id="exportBrowserProfile">Exportar meu perfil para o complemento</button>
    </div>
    <p id="browserProfileExportStatus" class="status cc-assistant-status" role="status" aria-live="polite"></p>
    <small class="hint">Salve o perfil antes de exportar. O arquivo contém seus dados profissionais e deve ser importado somente no seu próprio Chrome.</small>`;
  profileForm.insertAdjacentElement("afterend", card);

  const status = card.querySelector("#browserProfileExportStatus");
  const button = card.querySelector("#exportBrowserProfile");
  const cleanText = value => typeof value === "string" ? value.trim().slice(0, 12000) : "";

  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Preparando seu arquivo…";
    try {
      const response = await fetch("/profile", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Entre novamente e tente exportar o perfil.");
      const value = await response.json();
      if (!value.configured) throw new Error("Complete e salve seu perfil antes de exportar.");

      const profile = {
        name: cleanText(value.name),
        email: cleanText(value.email),
        phone: cleanText(value.phone),
        linkedin: cleanText(value.linkedin),
        website: cleanText(value.website),
        location: cleanText(value.location),
        headline: cleanText(value.headline),
        summary: cleanText(value.summary),
        experiences: Array.isArray(value.experience_items) ? value.experience_items.slice(0, 50).map(item => ({
          role: cleanText(item.role), company: cleanText(item.company), period: cleanText(item.period), description: cleanText(item.description)
        })) : [],
        education: Array.isArray(value.education_items) ? value.education_items.slice(0, 50).map(item => ({
          course: cleanText(item.course || item.title), institution: cleanText(item.institution), period: cleanText(item.period)
        })) : [],
        skills: Array.isArray(value.skill_items) ? value.skill_items.slice(0, 100).map(cleanText).filter(Boolean) : [],
        languages: Array.isArray(value.language_items) ? value.language_items.slice(0, 30).map(cleanText).filter(Boolean) : []
      };
      if (!profile.name && !profile.email && !profile.phone) throw new Error("Seu perfil ainda não tem dados para exportar.");

      const blob = new Blob([JSON.stringify({ schema_version: 1, generated_at: new Date().toISOString(), profile }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "candidatura-certa-perfil.json";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = "Arquivo exportado. Importe-o no complemento do Chrome quando estiver pronto para preencher uma candidatura.";
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Não foi possível exportar o perfil.";
    } finally {
      button.disabled = false;
    }
  });
})();
