(() => {
  const profileForm = document.querySelector("#profileForm");
  const extractedForm = document.querySelector("#extractedForm");
  if (!profileForm || !extractedForm) return;

  const style = document.createElement("style");
  style.textContent = ".cc-assistant-note{margin:12px 0 16px}.cc-assistant-actions{justify-content:flex-start;flex-wrap:wrap}.cc-assistant-status{margin:12px 0 0}.cc-assistant-steps{margin:12px 0;padding-left:22px;color:#52647c;line-height:1.6}.cc-assistant-steps code{font-size:.92em}";
  document.head.append(style);

  const card = document.createElement("section");
  card.className = "card";
  card.setAttribute("aria-labelledby", "browser-assistant-title");
  card.innerHTML = `
    <h2 id="browser-assistant-title">Copiloto no navegador</h2>
    <p>Conecte o complemento para preparar campos vazios da sua candidatura na Gupy, Vagas.com e InfoJobs. Você pode mostrar o botão uma vez ou autorizá-lo para aparecer automaticamente nas páginas de vagas reconhecidas daquele domínio.</p>
    <div class="tip cc-assistant-note">Você revisa os campos e clica em enviar no portal. O complemento não faz login, não responde perguntas abertas, não anexa documentos automaticamente e não resolve CAPTCHA. Use apenas se o portal permitir preenchimento assistido.</div>
    <div class="actions cc-assistant-actions">
      <a class="secondary" href="/static/candidatura-certa-autopreenchimento.zip?v=7" download>Baixar complemento para Chrome/Edge</a>
    </div>
    <details>
      <summary>Como instalar a versão de teste</summary>
      <ol class="cc-assistant-steps">
        <li>Extraia o ZIP para uma pasta do seu computador.</li>
        <li>Abra <code>chrome://extensions</code> (ou <code>edge://extensions</code>) e ative o modo de desenvolvedor.</li>
        <li>Escolha <strong>Carregar sem compactação</strong> e selecione a pasta extraída.</li>
        <li>Abra uma vaga compatível, clique no ícone do complemento e conecte sua conta.</li>
        <li>Confirme que o portal permite preenchimento assistido. Escolha mostrar o botão nesta página ou ativá-lo para páginas de vagas reconhecidas neste domínio.</li>
      </ol>
    </details>
    <p id="browserProfileExportStatus" class="status cc-assistant-status" role="status" aria-live="polite">O complemento está em distribuição de teste; a instalação pela loja oficial ainda não está publicada.</p>`;
  profileForm.insertAdjacentElement("afterend", card);
})();
