(function () {
  const wrap = document.querySelector('.wrap');
  if (!wrap) return;

  const style = document.createElement('style');
  style.textContent = `
    .security-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
    .security-grid .card{margin:0}
    .security-item{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;border-top:1px solid #dfe7f2}
    .security-item>div{min-width:0}
    .security-item strong,.security-item small{display:block}
    .security-item small{margin-top:3px;color:#64748b;line-height:1.45}
    .security-state{flex:0 0 auto;white-space:nowrap;font-size:11px;padding:4px 8px;border-radius:99px;color:#8a5a00;background:#fff5df}
    .security-state.active{color:#16794b;background:#eaf8f1}
    .security-state.error{color:#b42318;background:#fff1ef}
    .mfa-actions{margin-top:14px}
    .mfa-before-start{margin-top:16px;padding:14px 16px;border:1px solid #f2d28c;border-radius:12px;color:#684d13;background:#fffbeb;font-size:13px;line-height:1.5}
    .mfa-before-start strong{display:block;margin-bottom:5px}
    .mfa-before-start p{margin:4px 0}
    .mfa-state-help{margin-top:5px!important}
    .session-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 0;border-top:1px solid #dfe7f2}
    .session-row small{display:block;color:#64748b;margin-top:3px}
    .session-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
    .session-status{margin:12px 0 0;color:#16794b;font-size:13px;line-height:1.45}
    .session-status.error{color:#b42318}
    .session-note{margin:12px 0 0!important;font-size:12px!important;line-height:1.5}
    .security-action{padding:10px 14px;border:1px solid #dfe7f2;border-radius:9px;background:#fff;color:#3568e8;font-weight:800;font-size:13px}
    .security-action:hover:not(:disabled){background:#f5f8ff;transform:translateY(-1px)}
    .security-action:disabled{cursor:wait;opacity:.65}
    .security-action.active{color:#16794b}
    .security-action.danger{color:#b42318;border-color:#f3c4be}
    .notice-spaced{margin-top:14px}
    .mfa-dialog{width:min(520px,calc(100% - 28px));max-width:none;max-height:min(90vh,760px);padding:0;border:1px solid #d7e1ef;border-radius:18px;color:#10213d;background:#fff;box-shadow:0 24px 80px #10213d40}
    .mfa-dialog::backdrop{background:#10213d80;backdrop-filter:blur(3px)}
    .mfa-dialog__content{position:relative;padding:26px}
    .mfa-dialog__close{position:absolute;top:14px;right:14px;width:36px;height:36px;border:1px solid #dfe7f2;border-radius:9px;color:#334155;background:#fff;font-size:20px}
    .mfa-dialog h2{margin:0 44px 7px 0;font-size:21px}
    .mfa-dialog p{color:#52647e;line-height:1.5}
    .mfa-step-label{margin:0 0 14px;color:#3568e8!important;font-size:12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}
    .mfa-qr-frame{display:grid;place-items:center;min-height:190px;margin:16px auto;padding:12px;border:1px solid #dfe7f2;border-radius:14px;background:#fff}
    .mfa-qr{display:block;width:min(220px,100%);height:auto;max-height:220px;object-fit:contain}
    .mfa-qr[hidden]{display:none}
    .mfa-manual{margin:12px 0;border:1px solid #dfe7f2;border-radius:10px;padding:10px 12px}
    .mfa-manual summary{cursor:pointer;color:#315caa;font-weight:700;font-size:13px}
    .mfa-secret-row{display:flex;align-items:flex-start;gap:8px;margin-top:10px}
    .mfa-secret{min-width:0;flex:1;overflow-wrap:anywhere;padding:9px;border-radius:8px;background:#f4f7fb;font-family:ui-monospace,monospace;font-size:12px}
    .mfa-copy{flex:0 0 auto;padding:8px 10px;border:1px solid #dfe7f2;border-radius:8px;color:#315caa;background:#fff;font-weight:700}
    .mfa-device-confirm{display:flex;align-items:flex-start;gap:10px;margin:16px 0;padding:12px;border-radius:10px;background:#f4f7fb;color:#263b59;font-size:13px;line-height:1.45}
    .mfa-device-confirm input{margin-top:3px;flex:0 0 auto}
    .mfa-code-label{display:block;margin:18px 0 6px;font-size:13px;font-weight:750}
    .mfa-code{width:100%;padding:12px;border:1px solid #cbd7e7;border-radius:10px;text-align:center;font-size:22px;letter-spacing:.28em;font-variant-numeric:tabular-nums}
    .mfa-code:focus{outline:3px solid #dce8ff;border-color:#3568e8}
    .mfa-setup-status{min-height:22px;margin:8px 0 0;color:#52647e;font-size:13px}
    .mfa-setup-status.error{color:#b42318}
    .mfa-dialog__actions{display:flex;justify-content:flex-end;gap:10px;margin-top:14px}
    .mfa-dialog__actions .primary{border:0;color:#fff;background:#3568e8}
    .mfa-dialog__actions .primary:disabled{cursor:not-allowed;opacity:.55}
    @media(max-width:700px){.security-grid{grid-template-columns:1fr}}
    @media(max-width:520px){
      .security-item{align-items:flex-start;flex-direction:column;gap:8px}
      .security-state{align-self:flex-start}
      .mfa-dialog__content{padding:22px 18px}
      .mfa-dialog__actions{flex-direction:column-reverse}
      .mfa-dialog__actions button{width:100%}
    }
  `;
  document.head.appendChild(style);

  const grid = document.createElement('div');
  grid.className = 'security-grid';
  grid.innerHTML = `
    <section class="card mfa-card">
      <h2>Verificação em duas etapas</h2>
      <p>Opcional. Ao entrar, você usará sua senha e um código do aplicativo autenticador.</p>
      <div class="security-item">
        <div>
          <strong>Aplicativo autenticador</strong>
          <small>Google Authenticator, Microsoft Authenticator, 1Password ou similar.</small>
          <small class="mfa-state-help" data-mfa-help>Você pode ativar quando quiser.</small>
        </div>
        <span class="security-state" data-mfa-state aria-live="polite">Verificando…</span>
      </div>
      <div class="mfa-actions">
        <button class="security-action" type="button" data-mfa-action>Ativar verificação em duas etapas</button>
      </div>
      <div class="mfa-before-start">
        <strong>Antes de ativar</strong>
      <p>Tenha dois dispositivos confiáveis com um aplicativo autenticador. Durante a configuração, você adicionará a mesma conta nos dois. Se estiver no celular, use a chave manual para configurar os dois aparelhos.</p>
        <p>Não oferecemos recuperação por SMS nem códigos de emergência. Se perder acesso aos dois dispositivos, não conseguirá entrar.</p>
      </div>
    </section>
    <section class="card">
      <h2>Sessões e dispositivos</h2>
      <p>Veja o acesso deste navegador e encerre sessões abertas em outros dispositivos.</p>
      <div class="session-row"><div><strong>Este navegador</strong><small>Sessão atual</small></div><span class="security-state active">Conectado</span></div>
      <div class="session-actions">
        <button class="security-action" id="logoutOthers" type="button">Encerrar outras sessões</button>
        <button class="security-action danger" id="logoutCurrent" type="button">Sair deste dispositivo</button>
      </div>
      <p class="session-note">O app ainda não mostra os aparelhos individualmente. Ao encerrar as outras sessões, um dispositivo pode permanecer conectado até o token atual expirar.</p>
      <p class="session-status" id="sessionStatus" role="status" aria-live="polite" hidden></p>
    </section>`;
  const anchor = wrap.querySelector('.card');
  wrap.insertBefore(grid, anchor);

  const state = grid.querySelector('[data-mfa-state]');
  const help = grid.querySelector('[data-mfa-help]');
  const action = grid.querySelector('[data-mfa-action]');
  let factorId = '';
  let pendingFactorId = '';

  const dialog = document.createElement('dialog');
  dialog.className = 'mfa-dialog';
  dialog.setAttribute('aria-labelledby', 'mfaSetupTitle');
  dialog.innerHTML = `
    <div class="mfa-dialog__content">
      <button class="mfa-dialog__close" type="button" data-mfa-close aria-label="Fechar configuração">×</button>
      <p class="mfa-step-label">Configuração · 2 passos</p>
      <h2 id="mfaSetupTitle" tabindex="-1">Conecte seu aplicativo</h2>
      <p>Abra o aplicativo autenticador e escaneie este QR code. Repita no segundo dispositivo. Se estiver usando o próprio celular para acessar o site, abra a chave manual e cadastre-a nos dois aparelhos.</p>
      <div class="mfa-qr-frame"><img class="mfa-qr" data-mfa-qr alt="QR code para conectar o aplicativo autenticador" hidden><span data-mfa-qr-fallback>Use a chave manual abaixo para conectar seu aplicativo.</span></div>
      <details class="mfa-manual">
        <summary>Não consegue escanear? Mostrar chave manual</summary>
        <div class="mfa-secret-row"><code class="mfa-secret" data-mfa-secret></code><button class="mfa-copy" type="button" data-mfa-copy>Copiar chave</button></div>
        <p>Não compartilhe esta chave. Ela permite gerar códigos para entrar na sua conta.</p>
      </details>
      <label class="mfa-device-confirm"><input type="checkbox" data-mfa-second-device><span>Já adicionei esta mesma conta em um segundo dispositivo confiável.</span></label>
      <label class="mfa-code-label" for="mfaSetupCode">Passo 2 · Digite o código de 6 dígitos</label>
      <input class="mfa-code" id="mfaSetupCode" data-mfa-code type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="000000" aria-describedby="mfaSetupStatus" required>
      <p class="mfa-setup-status" data-mfa-setup-status role="status" aria-live="polite"></p>
      <div class="mfa-dialog__actions"><button class="secondary" type="button" data-mfa-cancel>Cancelar</button><button class="primary" type="button" data-mfa-confirm disabled>Confirmar e ativar</button></div>
    </div>`;
  document.body.appendChild(dialog);

  const qr = dialog.querySelector('[data-mfa-qr]');
  const qrFallback = dialog.querySelector('[data-mfa-qr-fallback]');
  const secretOutput = dialog.querySelector('[data-mfa-secret]');
  const copySecretButton = dialog.querySelector('[data-mfa-copy]');
  const secondDevice = dialog.querySelector('[data-mfa-second-device]');
  const codeInput = dialog.querySelector('[data-mfa-code]');
  const setupStatus = dialog.querySelector('[data-mfa-setup-status]');
  const confirmButton = dialog.querySelector('[data-mfa-confirm]');

  const setMfaState = (enabled, id) => {
    factorId = id || '';
    state.textContent = enabled ? 'Ativado' : 'Desativado';
    state.classList.toggle('active', enabled);
    state.classList.remove('error');
    help.textContent = enabled
      ? 'No próximo login, você também vai informar um código do aplicativo.'
      : 'A proteção é opcional e pode ser ativada quando quiser.';
    action.textContent = enabled ? 'Desativar verificação em duas etapas' : 'Ativar verificação em duas etapas';
    action.classList.toggle('active', !enabled);
    action.classList.toggle('danger', enabled);
    action.disabled = false;
  };

  const readJson = async (response, fallback) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || fallback);
    return payload;
  };

  const loadMfaStatus = async () => {
    try {
      const response = await fetch('/auth/mfa/status');
      const payload = await readJson(response, 'Não foi possível verificar a proteção agora.');
      const factor = (payload.factors || []).find(item => item.status === 'verified');
      setMfaState(Boolean(factor), factor && factor.id);
    } catch (error) {
      state.textContent = 'Não foi possível verificar';
      state.classList.add('error');
      action.disabled = true;
      action.title = error.message;
    }
  };

  const setSetupMessage = (message, isError = false) => {
    setupStatus.textContent = message;
    setupStatus.classList.toggle('error', isError);
  };

  const cancelSetup = async () => {
    const id = pendingFactorId;
    pendingFactorId = '';
    if (dialog.open) dialog.close();
    if (id) {
      try {
        await fetch('/auth/mfa/' + encodeURIComponent(id), { method: 'DELETE' });
      } catch (_) {
        // An unfinished factor does not grant access; status is refreshed below.
      }
    }
    await loadMfaStatus();
  };

  const openSetup = factor => {
    pendingFactorId = factor.id;
    codeInput.value = '';
    secondDevice.checked = false;
    confirmButton.disabled = true;
    setSetupMessage('Escaneie o QR code nos dois dispositivos e digite o código atual.');
    const qrValue = typeof factor.qr_code === 'string' ? factor.qr_code : '';
    const safeQrValue = /^data:image\/(?:svg\+xml|png|jpeg|webp);/i.test(qrValue) ? qrValue : '';
    qr.hidden = !safeQrValue;
    qrFallback.hidden = Boolean(safeQrValue);
    if (safeQrValue) qr.src = safeQrValue;
    secretOutput.textContent = typeof factor.secret === 'string' ? factor.secret : '';
    copySecretButton.hidden = !secretOutput.textContent;
    if (!secretOutput.textContent) secretOutput.textContent = 'Chave manual indisponível';
    dialog.showModal();
    dialog.querySelector('#mfaSetupTitle').focus();
  };

  const configureMfa = async () => {
    action.disabled = true;
    action.textContent = 'Preparando configuração…';
    try {
      const response = await fetch('/auth/mfa/enroll', { method: 'POST' });
      const factor = await readJson(response, 'Não foi possível iniciar a configuração. Tente novamente.');
      if (!factor.id) throw new Error('Não foi possível iniciar a configuração. Tente novamente.');
      openSetup(factor);
    } catch (error) {
      state.textContent = 'Falha ao iniciar';
      state.classList.add('error');
      help.textContent = error.message || 'Não foi possível iniciar agora. Tente novamente.';
    } finally {
      action.disabled = false;
      action.textContent = factorId ? 'Desativar verificação em duas etapas' : 'Ativar verificação em duas etapas';
    }
  };

  const verifySetup = async () => {
    const code = codeInput.value.trim();
    if (!secondDevice.checked) {
      setSetupMessage('Adicione a conta no segundo dispositivo antes de confirmar.', true);
      secondDevice.focus();
      return;
    }
    if (!/^\d{6}$/.test(code)) {
      setSetupMessage('Digite os 6 números exibidos no aplicativo autenticador.', true);
      codeInput.focus();
      return;
    }
    confirmButton.disabled = true;
    setSetupMessage('Verificando o código…');
    try {
      const challengeResponse = await fetch('/auth/mfa/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ factor_id: pendingFactorId }),
      });
      const challenge = await readJson(challengeResponse, 'Não foi possível verificar agora. Tente novamente.');
      const verifyResponse = await fetch('/auth/mfa/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ factor_id: pendingFactorId, challenge_id: challenge.id, code }),
      });
      const result = await readJson(verifyResponse, 'O código não foi aceito. Confira o aplicativo e tente de novo.');
      const verifiedId = pendingFactorId;
      pendingFactorId = '';
      setMfaState(true, verifiedId);
      if (dialog.open) dialog.close();
      if (result.reauth_required) {
        state.textContent = 'Ativado · entre novamente para concluir';
        help.textContent = 'Sua proteção foi ativada. Entre novamente e informe o código do aplicativo.';
        window.setTimeout(() => { window.location.href = '/'; }, 1800);
      } else {
        state.textContent = 'Ativado';
      }
    } catch (error) {
      setSetupMessage(error.message || 'Não foi possível confirmar. Tente novamente.', true);
      confirmButton.disabled = false;
      codeInput.focus();
    }
  };

  secondDevice.addEventListener('change', () => {
    confirmButton.disabled = !secondDevice.checked;
    if (secondDevice.checked && setupStatus.classList.contains('error')) setSetupMessage('Digite o código atual para concluir.');
  });
  codeInput.addEventListener('input', () => {
    codeInput.value = codeInput.value.replace(/\D/g, '').slice(0, 6);
  });
  confirmButton.addEventListener('click', verifySetup);
  dialog.querySelector('[data-mfa-close]').addEventListener('click', cancelSetup);
  dialog.querySelector('[data-mfa-cancel]').addEventListener('click', cancelSetup);
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    cancelSetup();
  });
  copySecretButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(secretOutput.textContent);
      setSetupMessage('Chave copiada. Não a compartilhe.');
    } catch (_) {
      setSetupMessage('Não foi possível copiar. Selecione a chave e copie manualmente.', true);
    }
  });

  action.addEventListener('click', async () => {
    if (!factorId) return configureMfa();
    if (!window.confirm('Desativar a verificação em duas etapas desta conta?')) return;
    action.disabled = true;
    action.textContent = 'Desativando…';
    try {
      const response = await fetch('/auth/mfa/' + encodeURIComponent(factorId), { method: 'DELETE' });
      await readJson(response, 'Não foi possível desativar agora. Tente novamente.');
      setMfaState(false, '');
    } catch (error) {
      state.textContent = error.message;
      state.classList.add('error');
      await loadMfaStatus();
    }
  });

  const sessionStatus = grid.querySelector('#sessionStatus');
  const setSessionStatus = (message, isError = false) => {
    sessionStatus.textContent = message;
    sessionStatus.classList.toggle('error', isError);
    sessionStatus.hidden = false;
  };

  const logoutCurrent = grid.querySelector('#logoutCurrent');
  logoutCurrent.addEventListener('click', async () => {
    if (!window.confirm('Sair deste navegador? As sessões em outros dispositivos continuarão conectadas.')) return;
    logoutCurrent.disabled = true;
    logoutCurrent.textContent = 'Encerrando…';
    try {
      const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
      await readJson(response, 'Não foi possível encerrar esta sessão agora.');
      window.location.href = '/?signed_out=1';
    } catch (error) {
      setSessionStatus(error.message, true);
      logoutCurrent.disabled = false;
      logoutCurrent.textContent = 'Sair deste dispositivo';
    }
  });

  const logoutOthers = grid.querySelector('#logoutOthers');
  logoutOthers.addEventListener('click', async () => {
    if (!window.confirm('Encerrar as sessões em todos os outros navegadores e dispositivos? Este navegador continuará conectado.')) return;
    logoutOthers.disabled = true;
    logoutOthers.textContent = 'Encerrando…';
    sessionStatus.hidden = true;
    try {
      const response = await fetch('/auth/logout/others', { method: 'POST', credentials: 'same-origin' });
      const payload = await readJson(response, 'Não foi possível encerrar as outras sessões agora.');
      setSessionStatus(payload.detail || 'Outras sessões encerradas. Este navegador continua conectado.');
    } catch (error) {
      setSessionStatus(error.message, true);
    } finally {
      logoutOthers.disabled = false;
      logoutOthers.textContent = 'Encerrar outras sessões';
    }
  });

  const exportButton = document.querySelector('#exportData');
  const exportStatus = document.querySelector('#exportStatus');
  if (exportButton) {
    exportButton.addEventListener('click', async () => {
      exportButton.disabled = true;
      if (exportStatus) exportStatus.textContent = 'Preparando seus dados…';
      try {
        const response = await fetch('/api/privacy/export', { credentials: 'same-origin' });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || 'Não foi possível exportar seus dados agora.');
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'agente-de-candidaturas-dados.json';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        if (exportStatus) exportStatus.textContent = 'Download iniciado.';
      } catch (error) {
        if (exportStatus) exportStatus.textContent = error.message || 'Não foi possível exportar seus dados agora.';
      } finally {
        exportButton.disabled = false;
      }
    });
  }

  loadMfaStatus();
})();
