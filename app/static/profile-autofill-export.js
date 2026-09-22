(() => {
  const profileForm = document.querySelector("#profileForm");
  const extractedForm = document.querySelector("#extractedForm");
  if (!profileForm || !extractedForm) return;

  const style = document.createElement("style");
  style.textContent = ".cc-assistant-note{margin:12px 0 16px}.cc-assistant-actions{justify-content:flex-start;flex-wrap:wrap}.cc-assistant-actions .primary{display:inline-flex;align-items:center;justify-content:center;text-decoration:none}.cc-assistant-status{margin:12px 0 0}.cc-assistant-guide{margin-top:16px;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fbfdff}.cc-assistant-guide>summary{font-weight:800;cursor:pointer}.cc-assistant-steps{display:grid;gap:12px;margin:14px 0 0;padding-left:24px;color:#52647c;line-height:1.55}.cc-assistant-steps li{padding-left:4px}.cc-assistant-steps strong{color:var(--ink)}.cc-assistant-step-help{display:block;margin-top:4px;font-size:12px}.cc-assistant-copy{margin-top:8px}.cc-assistant-copy code{display:inline-block;padding:4px 7px;border-radius:6px;background:#eef2f8;font-size:12px}.cc-assistant-support{display:inline-flex;margin-top:10px;color:var(--blue);font-size:13px;font-weight:750;text-decoration:underline}.cc-assistant-status{line-height:1.5}@media(min-width:760px){.cc-assistant-steps{grid-template-columns:1fr 1fr;column-gap:24px}}";
  document.head.append(style);

  const card = document.createElement("section");
  card.className = "card";
  card.setAttribute("aria-labelledby", "browser-assistant-title");
  card.innerHTML = `
    <h2 id="browser-assistant-title">Preencha alguns dados da vaga com o copiloto</h2>
    <p>O copiloto pode levar para o formulário da Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br as informações que você já salvou no seu perfil. Você confere tudo e envia no próprio portal.</p>
    <div class="tip cc-assistant-note"><strong>Copiloto — versão estável 1.0.1:</strong> o pacote final para Chrome e Edge está pronto. A instalação pública pela loja oficial ainda aguarda publicação; até lá, a instalação é manual neste computador. Depois de instalar uma vez, basta abrir uma vaga compatível e pedir para preparar os campos. O complemento não envia candidaturas nem resolve CAPTCHA e funciona no computador, não no aplicativo do celular.</div>
    <div class="actions cc-assistant-actions">
      <a class="primary" href="/static/candidatura-certa-autopreenchimento.zip?v=11" download>Baixar o copiloto 1.0.1</a>
    </div>
    <details class="cc-assistant-guide" open>
      <summary>Instalar no computador — faça isso uma vez</summary>
      <ol class="cc-assistant-steps">
        <li><strong>Baixe o copiloto.</strong><span class="cc-assistant-step-help">O arquivo vai para a pasta Downloads do seu computador.</span></li>
        <li><strong>Abra o arquivo que baixou.</strong><span class="cc-assistant-step-help">No Windows: abra Downloads, clique com o botão direito no ZIP e escolha “Extrair tudo”. No Mac, abra o ZIP para criar a pasta.</span></li>
        <li><strong>Abra as extensões do seu navegador.</strong><span class="cc-assistant-step-help">Copie o endereço abaixo, abra uma nova aba, cole-o na barra de endereços e pressione Enter. Depois, ligue “Modo do desenvolvedor”.</span><div class="cc-assistant-copy"><code id="ccExtensionsAddress">chrome://extensions</code> <button class="secondary" id="ccCopyExtensionsAddress" type="button">Copiar endereço</button></div></li>
        <li><strong>Adicione o copiloto.</strong><span class="cc-assistant-step-help">Clique em “Carregar sem compactação” (ou opção parecida) e escolha a pasta que saiu do ZIP.</span></li>
        <li><strong>Conecte sua conta.</strong><span class="cc-assistant-step-help">Abra uma vaga, clique no ícone de extensões do navegador (peça de quebra-cabeça no Chrome), escolha Candidatura Certa e siga “Conectar minha conta”.</span></li>
        <li><strong>Prepare a vaga.</strong><span class="cc-assistant-step-help">Confirme que o portal permite preenchimento assistido. Revise os dados antes de clicar em Enviar no próprio portal.</span></li>
      </ol>
    </details>
    <p id="browserProfileExportStatus" class="status cc-assistant-status" role="status" aria-live="polite">Se algum passo não corresponder ao que aparece na sua tela, fale com o suporte pelo WhatsApp (71) 99182-4951.</p>
    <a class="cc-assistant-support" href="https://wa.me/5571991824951?text=Preciso%20de%20ajuda%20para%20instalar%20o%20copiloto%20da%20Candidatura%20Certa" target="_blank" rel="noopener noreferrer">Preciso de ajuda para instalar</a>`;
  profileForm.insertAdjacentElement("afterend", card);

  const extensionsAddress = /Edg\//.test(navigator.userAgent) ? "edge://extensions" : "chrome://extensions";
  const address = card.querySelector("#ccExtensionsAddress");
  const copyButton = card.querySelector("#ccCopyExtensionsAddress");
  const status = card.querySelector("#browserProfileExportStatus");
  address.textContent = extensionsAddress;
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(extensionsAddress);
      status.textContent = "Endereço copiado. Abra uma nova aba, cole na barra de endereços e pressione Enter.";
    } catch {
      status.textContent = `Abra uma nova aba e digite este endereço na barra de endereços: ${extensionsAddress}`;
    }
  });
})();
