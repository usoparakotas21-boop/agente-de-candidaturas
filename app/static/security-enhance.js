(function(){
  const wrap=document.querySelector('.wrap');
  if(!wrap)return;

  const style=document.createElement('style');
  style.textContent='.security-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.security-grid .card{margin:0}.security-item{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;border-top:1px solid #dfe7f2}.security-item:first-child{border-top:0}.security-item>div{min-width:0}.security-item strong,.security-item small{display:block}.security-item small{margin-top:3px;color:#64748b;line-height:1.45}.security-state{flex:0 0 auto;font-size:11px;padding:4px 8px;border-radius:99px;color:#a15c00;background:#fff5df}.security-state.active{color:#16794b;background:#eaf8f1}.security-state.error{color:#b42318;background:#fff1ef}.session-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 0;border-top:1px solid #dfe7f2}.session-row small{display:block;color:#64748b;margin-top:3px}.security-action{padding:9px 12px;border:1px solid #dfe7f2;border-radius:9px;background:#fff;color:#3568e8;font-weight:800;font-size:12px}.security-action.active{color:#16794b}.security-action.danger{color:#b42318;border-color:#f3c4be}.notice-spaced{margin-top:14px}@media(max-width:700px){.security-grid{grid-template-columns:1fr}}';
  document.head.appendChild(style);

  const grid=document.createElement('div');
  grid.className='security-grid';
  grid.innerHTML='<section class="card"><h2>Autenticação em dois fatores</h2><p>Proteja sua conta mesmo que sua senha seja descoberta.</p><div class="security-item"><div><strong>Aplicativo autenticador</strong><small>Use Google Authenticator, 1Password ou similar.</small></div><span class="security-state" data-mfa-state>Verificando…</span></div><div class="security-item"><div><strong>SMS de backup</strong><small>Usado apenas como recuperação.</small></div><span class="security-state">Opcional</span></div><div class="mfa-actions"><button class="security-action" type="button" data-mfa-action>Configurar autenticador</button></div><div class="notice notice-spaced">Ao ativar, você receberá códigos de recuperação para guardar offline. A autenticação em dois fatores é opcional e pode ser desativada nesta tela.</div></section><section class="card"><h2>Sessões ativas</h2><p>Revise os dispositivos que estão usando sua conta.</p><div class="session-row"><div><strong>Este dispositivo</strong><small>Navegador atual · sessão ativa</small></div><span class="security-state active">Ativa</span></div><button class="security-action" id="logoutAll" type="button">Sair deste dispositivo</button><div class="notice notice-spaced">O encerramento de todas as sessões será disponibilizado quando o provedor de autenticação permitir revogação global.</div></section>';
  const anchor=wrap.querySelector('.card');
  wrap.insertBefore(grid,anchor);

  const state=grid.querySelector('[data-mfa-state]');
  const action=grid.querySelector('[data-mfa-action]');
  let factorId='';

  const setMfaState=(enabled,id)=>{
    factorId=id||'';
    state.textContent=enabled?'Ativo':'Não configurado';
    state.classList.toggle('active',enabled);
    state.classList.remove('error');
    action.textContent=enabled?'Desativar autenticador':'Configurar autenticador';
    action.classList.toggle('active',!enabled);
    action.classList.toggle('danger',enabled);
    action.disabled=false;
  };

  const loadMfaStatus=async()=>{
    try{
      const response=await fetch('/auth/mfa/status');
      const payload=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(payload.detail||'Não foi possível verificar o segundo fator agora.');
      const factor=(payload.factors||[]).find(item=>item.status==='verified');
      setMfaState(Boolean(factor),factor&&factor.id);
    }catch(error){
      state.textContent='Indisponível';
      state.classList.add('error');
      action.disabled=true;
      action.title=error.message;
    }
  };

  const configureMfa=async()=>{
    action.disabled=true;
    action.textContent='Gerando configuração…';
    try{
      const response=await fetch('/auth/mfa/enroll',{method:'POST'});
      const factor=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(factor.detail||'Não foi possível iniciar o 2FA.');
      const code=prompt('Abra seu autenticador e adicione a conta. Segredo: '+(factor.secret||factor.uri||'')+' . Depois, digite o código de 6 dígitos para confirmar:');
      if(!code)throw Error('cancel');
      const challengeResponse=await fetch('/auth/mfa/challenge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({factor_id:factor.id})});
      const challenge=await challengeResponse.json().catch(()=>({}));
      if(!challengeResponse.ok)throw Error(challenge.detail||'Não foi possível iniciar a verificação 2FA.');
      const verifyResponse=await fetch('/auth/mfa/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({factor_id:factor.id,challenge_id:challenge.id,code:code.trim()})});
      const result=await verifyResponse.json().catch(()=>({}));
      if(!verifyResponse.ok)throw Error(result.detail||'Código 2FA inválido.');
      setMfaState(true,factor.id);
    }catch(error){
      if(error.message!=='cancel')alert(error.message);
      await loadMfaStatus();
    }
  };

  const disableMfa=async()=>{
    if(!factorId)return loadMfaStatus();
    if(!confirm('Desativar a autenticação em dois fatores desta conta?'))return;
    action.disabled=true;
    action.textContent='Desativando…';
    try{
      const response=await fetch('/auth/mfa/'+encodeURIComponent(factorId),{method:'DELETE'});
      const result=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(result.detail||'Não foi possível remover o autenticador.');
      setMfaState(false,'');
    }catch(error){
      alert(error.message);
      await loadMfaStatus();
    }
  };

  action.addEventListener('click',()=>factorId?disableMfa():configureMfa());
  grid.querySelector('#logoutAll').addEventListener('click',()=>{fetch('/auth/logout',{method:'POST'}).finally(()=>location.href='/')});
  loadMfaStatus();
})();
