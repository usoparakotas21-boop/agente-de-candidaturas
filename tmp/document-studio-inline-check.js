const $=id=>document.getElementById(id);
    let current=null;
    let linkedApplicationId=null;
    let paymentReturnHandled=false;
    const pendingExportStorageKey='candidatura-certa.pending-export';
    function savePendingExport(applicationId){
      try{
        const id=Number(applicationId);
        if(!Number.isSafeInteger(id)||id<1)return;
        localStorage.setItem(pendingExportStorageKey,JSON.stringify({application_id:id,created_at:Date.now()}));
      }catch{ /* armazenamento local indisponível não impede o checkout */ }
    }
    function readPendingExport(){
      try{
        const raw=localStorage.getItem(pendingExportStorageKey);
        if(!raw)return null;
        const value=JSON.parse(raw);
        const id=Number(value?.application_id),created=Number(value?.created_at);
        if(!Number.isSafeInteger(id)||id<1||!Number.isFinite(created)||Date.now()-created>7*24*60*60*1000){
          localStorage.removeItem(pendingExportStorageKey);
          return null;
        }
        return id;
      }catch{return null}
    }
    function clearPendingExport(applicationId){
      try{
        const id=Number(applicationId),value=readPendingExport();
        if(!applicationId||value===id)localStorage.removeItem(pendingExportStorageKey);
      }catch{ /* armazenamento local indisponível */ }
    }
    let emailPreview=null;

    function msg(text,ok=false){
      $('status').textContent=text;
      $('status').className='status'+(ok?' ok':'');
    }
    function checkoutMsg(text,ok=false){
      $('checkoutStatus').textContent=text;
      $('checkoutStatus').className='status'+(ok?' ok':'');
    }
    function renderQuickCopy(blocks){
      const panel=$('quickCopyPanel'),actions=$('quickCopyActions'),status=$('quickCopyStatus');
      actions.replaceChildren();
      status.textContent='';
      const labels={headline:'título profissional',summary:'resumo',skills:'competências',experience:'experiência',education:'formação'};
      const available=Object.entries(labels).filter(([key])=>String(blocks?.[key]||'').trim());
      panel.hidden=!available.length;
      for(const [key,label] of available){
        const button=document.createElement('button');
        button.type='button';button.textContent='Copiar '+label;
        button.addEventListener('click',async()=>{
          try{
            const value=String(blocks[key]||'').trim();
            if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(value);
            else{const temporary=document.createElement('textarea');temporary.value=value;temporary.setAttribute('readonly','');temporary.style.position='fixed';temporary.style.opacity='0';document.body.append(temporary);temporary.select();const copied=document.execCommand('copy');temporary.remove();if(!copied)throw new Error('clipboard_unavailable')}
            status.textContent='Bloco de '+label+' copiado. Revise antes de colar no portal.';
          }catch{status.textContent='Não foi possível copiar automaticamente. Selecione e copie o texto da prévia.'}
        });
        actions.append(button);
      }
    }
    function selectedEmailSubmission(){
      const recipient=$('emailRecipient').value;
      return emailPreview?.submission_statuses?.find(item=>item.recipient===recipient)||null;
    }
    function updateEmailSubmissionControls(){
      const recipient=$('emailRecipient').value;
      const record=selectedEmailSubmission();
      const blocked=['SENT','SENDING','UNKNOWN'].includes(record?.status);
      const ready=Boolean(emailPreview&&recipient&&emailPreview.smtp_configured&&emailPreview.account_email_verified&&$('emailConsent').checked&&$('emailBody').value.trim().length>=20&&!blocked);
      $('sendEmailApplication').disabled=!ready;
      if(record?.status==='SENT')$('emailAssistStatus').textContent='Este endereço já recebeu a candidatura. O envio não será repetido.';
      else if(record?.status==='UNKNOWN')$('emailAssistStatus').textContent='O servidor não confirmou o resultado. Confira sua caixa de enviados e não repita o envio.';
      else if(record?.status==='SENDING')$('emailAssistStatus').textContent='Há um envio em andamento para este endereço. Aguarde a confirmação.';
      else if(record?.status==='FAILED')$('emailAssistStatus').textContent=record.last_error||'A conexão falhou antes do envio. Você pode revisar e tentar novamente.';
      else if(emailPreview&&!emailPreview.smtp_configured)$('emailAssistStatus').textContent='O envio por e-mail ainda não está configurado. Nenhuma mensagem foi enviada; você pode baixar os PDFs.';
      else if(emailPreview&&!emailPreview.account_email_verified)$('emailAssistStatus').textContent='Confirme o e-mail da sua conta antes de enviar uma candidatura.';
      else if(emailPreview&&!emailPreview.recipients?.length)$('emailAssistStatus').textContent='Não encontramos um endereço de e-mail no anúncio. Use o portal da empresa ou preencha os dados manualmente.';
      else if(emailPreview&&recipient&&!$('emailConsent').checked)$('emailAssistStatus').textContent='Marque a autorização depois de revisar o endereço, a mensagem e os anexos.';
      else if(emailPreview&&recipient&&!blocked)$('emailAssistStatus').textContent='A mensagem será enviada pelo endereço da Candidatura Certa; respostas irão para o e-mail confirmado da sua conta.';
    }
    async function loadEmailSubmissionPreview(){
      const panel=$('emailApplicationPanel');
      if(!current?.application_id){panel.hidden=true;return}
      panel.hidden=false;
      emailPreview=null;
      $('emailConsent').checked=false;
      $('emailRecipient').replaceChildren(new Option('Carregando endereços…',''));
      $('emailBody').value='';
      $('emailAttachments').textContent='';
      $('emailAssistStatus').textContent='Preparando a prévia e conferindo os documentos…';
      $('sendEmailApplication').disabled=true;
      try{
        const response=await fetch(`/applications/${encodeURIComponent(current.application_id)}/email-submission/preview`,{cache:'no-store'});
        const data=await response.json();
        if(!response.ok)throw new Error(data.detail||'Não foi possível preparar o envio por e-mail.');
        emailPreview=data;
        const addresses=Array.isArray(data.recipients)?data.recipients:[];
        $('emailRecipient').replaceChildren(new Option(addresses.length?'Selecione o destinatário':'Nenhum endereço encontrado',''));
        for(const address of addresses)$('emailRecipient').append(new Option(address,address));
        $('emailBody').value=data.body||'';
        const attachmentNames=(data.attachments||[]).map(item=>item.name).join(' · ');
        $('emailAttachments').textContent='Assunto: '+(data.subject||'Candidatura')+' · Anexos PDF: '+(attachmentNames||'indisponíveis');
        $('emailAssistStatus').textContent='';
        updateEmailSubmissionControls();
      }catch(error){
        emailPreview=null;
        $('emailAssistStatus').textContent=error.message||'Não foi possível preparar a prévia. Seus documentos continuam disponíveis para download.';
        $('sendEmailApplication').disabled=true;
      }
    }
    async function sendReviewedEmailApplication(){
      if(!current?.application_id||!emailPreview||$('sendEmailApplication').disabled)return;
      const button=$('sendEmailApplication');
      button.disabled=true;button.textContent='Enviando candidatura…';
      $('emailAssistStatus').textContent='Enviando somente para o endereço que você revisou…';
      try{
        const response=await fetch(`/applications/${encodeURIComponent(current.application_id)}/email-submission/send`,{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({recipient:$('emailRecipient').value,body:$('emailBody').value,resume_version:emailPreview.resume_version,cover_letter_version:emailPreview.cover_letter_version,consent:true})
        });
        const data=await response.json();
        if(!response.ok)throw new Error(data.detail||'Não foi possível concluir o envio.');
        $('emailConsent').checked=false;
        $('emailAssistStatus').textContent=data.message||'Resultado do envio atualizado.';
        await loadEmailSubmissionPreview();
      }catch(error){
        $('emailAssistStatus').textContent=error.message||'O envio não foi confirmado. Atualize a prévia antes de tentar novamente.';
        try{await loadEmailSubmissionPreview()}catch{}
      }finally{button.textContent='Enviar candidatura revisada';updateEmailSubmissionControls()}
    }
    async function loadDocumentPdfLinks(applicationId){
      try{
        const response=await fetch('/api/documents',{cache:'no-store'});
        if(!response.ok)return;
        const data=await response.json();
        const item=(data.items||[]).find(entry=>Number(entry.application_id)===Number(applicationId)&&entry.resume?.download_pdf_url&&entry.cover_letter?.download_pdf_url);
        if(!item)return;
        $('downloadResumePdf').dataset.url=item.resume.download_pdf_url;
        $('downloadLetterPdf').dataset.url=item.cover_letter.download_pdf_url;
        $('downloadResumePdf').hidden=false;$('downloadLetterPdf').hidden=false;
      }catch{}
    }
    function updateApplyLink(value){
      const link=$('openJobAfterPrepare');
      try{
        const url=new URL(String(value||''));
        if(!['http:','https:'].includes(url.protocol))throw new Error('URL não permitida');
        link.href=url.href;
        link.hidden=false;
      }catch{
        link.removeAttribute('href');
        link.hidden=true;
      }
    }
    function showExport(offer){
      const actions=$('exportActions');
      actions.hidden=false;
      updateApplyLink($('url').value);
      const paid=Boolean(offer&&offer.allowed);
      $('checkout').hidden=paid;
      $('refreshAccess').hidden=paid;
      $('retryGeneration').hidden=true;
      // Entitlement only proves that generation is permitted; one-time paid
      // purchases may still be processing on the server. Reveal downloads only
      // after the server reports READY.
      $('downloadResume').hidden=true;
      $('downloadLetter').hidden=true;
      $('notice').textContent=paid
        ?'Seu acesso está liberado. Os documentos completos aparecem para download assim que a geração terminar.'
        :(offer&&offer.price
          ?'Prévia gratuita ativa. O currículo e a carta completos podem ser liberados por '+offer.price+'.'
          :'Prévia gratuita. O arquivo completo está incluído no Start e no Pro, ou pode ser comprado à parte.');
    }
    async function getOffer(applicationId=linkedApplicationId){
      const query=applicationId?'?application_id='+encodeURIComponent(applicationId):'';
      const r=await fetch('/billing/document-export'+query);
      return r.ok?r.json():{allowed:false};
    }
    async function getPurchaseGeneration(applicationId){
      if(!applicationId)return null;
      const r=await fetch('/billing/document-export/status?application_id='+encodeURIComponent(applicationId));
      if(!r.ok)throw new Error('Não foi possível consultar a geração dos documentos.');
      return r.json();
    }
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    function showGeneratedDocuments(data,offer){
      current=Object.assign({},current||{},{application_id:data.application_id});
      renderQuickCopy(current.quick_copy);
      showExport(Object.assign({},offer||{}, {allowed:true}));
      $('downloadResume').dataset.url=data.resume_url||('/applications/'+data.application_id+'/document');
      $('downloadLetter').dataset.url=data.letter_url||('/applications/'+data.application_id+'/cover-letter/document');
      $('downloadResume').hidden=false;
      $('downloadLetter').hidden=false;
      $('retryGeneration').hidden=true;
      checkoutMsg(data.message||'Pagamento confirmado. Currículo e carta estão prontos para baixar.',true);
      msg('Documentos liberados após a confirmação do pagamento.',true);
      loadDocumentPdfLinks(data.application_id);
      loadEmailSubmissionPreview();
    }
    async function waitForServerGeneration(applicationId,offer,{timeout=90000}={}){
      const deadline=Date.now()+timeout;
      let state=await getPurchaseGeneration(applicationId);
      if(state.purchase_status==='NONE'||state.entitlement_source==='plan')return {mode:'plan',state};
      if(state.purchase_status!=='PAID')return {mode:'waiting_payment',state};
      while(['WAITING','PROCESSING','RETRY'].includes(state.generation_status)&&Date.now()<deadline){
        checkoutMsg(state.message||'Pagamento confirmado. Preparando seus documentos…');
        await wait(1800);
        state=await getPurchaseGeneration(applicationId);
      }
      if(state.generation_status==='READY'){
        showGeneratedDocuments(state,offer);
        return {mode:'ready',state};
      }
      if(state.generation_status==='FAILED'){
        showExport(Object.assign({},offer||{}, {allowed:true}));
        $('retryGeneration').hidden=false;
        checkoutMsg(state.message||'Não foi possível gerar automaticamente. Seu pagamento continua válido.');
        return {mode:'failed',state};
      }
      showExport(Object.assign({},offer||{}, {allowed:true}));
      checkoutMsg(state.message||'Pagamento confirmado; a geração continua na fila. Volte depois e os documentos estarão salvos.');
      return {mode:'pending',state};
    }
    async function refreshAccess(){
      try{
        const offer=await getOffer();
        showExport(offer);
        if(offer.allowed&&linkedApplicationId){
          if(!current||Number(current.application_id)!==Number(linkedApplicationId))await generatePreview({scroll:false});
          const state=await waitForServerGeneration(linkedApplicationId,offer,{timeout:5000});
          if(state.mode==='plan')await exportPaidDocuments(offer);
        }else{
          checkoutMsg('Ainda não encontramos a confirmação. Se você acabou de pagar, aguarde alguns segundos e tente novamente.');
        }
      }catch(error){checkoutMsg(error.message||'Não foi possível atualizar o pagamento.')}
    }
    async function waitForPaidAccess(applicationId){
      const deadline=Date.now()+60000;
      let offer=await getOffer(applicationId);
      let purchase=await getPurchaseGeneration(applicationId);
      while(!offer.allowed&&Date.now()<deadline){
        checkoutMsg('Pagamento recebido. Aguardando a confirmação segura do Mercado Pago…');
        await wait(2500);
        purchase=await getPurchaseGeneration(applicationId);
        offer=await getOffer(applicationId);
      }
      return {offer,purchase:purchase&&purchase.purchase_status==='PAID'?purchase:null};
    }
    async function exportPaidDocuments(offer){
      if(!offer||!offer.allowed||!linkedApplicationId)return false;
      checkoutMsg('Pagamento confirmado. Gerando currículo e carta personalizados…');
      const r=await fetch('/document-studio/export',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({application_id:Number(linkedApplicationId)})
      });
      const data=await r.json();
      if(!r.ok)throw new Error(data.detail||'Não foi possível gerar os documentos.');
      if(data.generation_status==='READY'||data.status==='DOCUMENTOS_GERADOS'){
        showGeneratedDocuments(data,offer);
      }else if(data.generation_status==='FAILED'||data.status==='DOCUMENTOS_FALHARAM'){
        showExport(Object.assign({},offer,{allowed:true}));
        $('retryGeneration').hidden=false;
        checkoutMsg(data.message||'Não foi possível concluir a geração. Seu pagamento continua válido.');
      }else{
        await waitForServerGeneration(linkedApplicationId,offer);
      }
      return true;
    }
    async function restorePaidApplication(){
      if(!linkedApplicationId)return false;
      const offer=await getOffer(linkedApplicationId);
      if(!offer.allowed)return false;
      $('result').classList.add('visible');
      const state=await waitForServerGeneration(linkedApplicationId,offer,{timeout:5000});
      if(state.mode==='plan'){
        if(!current||Number(current.application_id)!==Number(linkedApplicationId))await generatePreview({scroll:false});
        await exportPaidDocuments(offer);
      }
      if(state.mode==='ready'||state.mode==='plan'&&!$('downloadResume').hidden){
        clearPendingExport(linkedApplicationId);
      }
      return true;
    }
    let pendingRestoreInFlight=false;
    let lastPendingRestoreAt=0;
    async function restorePendingCheckoutOnFocus(){
      const pendingId=readPendingExport();
      if(!pendingId||pendingRestoreInFlight||paymentReturnHandled||Number(linkedApplicationId)!==Number(pendingId))return;
      const now=Date.now();
      if(now-lastPendingRestoreAt<5000)return;
      lastPendingRestoreAt=now;
      pendingRestoreInFlight=true;
      try{
        const restored=await restorePaidApplication();
        if(restored)msg('Verificamos novamente o pagamento e a geração dos documentos.',true);
      }catch(error){checkoutMsg(error.message||'Não foi possível atualizar o pagamento agora.');}
      finally{pendingRestoreInFlight=false;}
    }
    async function handlePaymentReturn(){
      if(paymentReturnHandled)return;
      const params=new URLSearchParams(window.location.search);
      const requested=params.get('application_id');
      const paymentStatus=(params.get('payment_status')||'').toLowerCase();
      if(!requested||!paymentStatus)return;
      paymentReturnHandled=true;
      if(paymentStatus==='failure'){
        clearPendingExport(requested);
        checkoutMsg('O pagamento não foi concluído. Você pode tentar novamente.');
        return;
      }
      $('result').classList.add('visible');
      checkoutMsg(paymentStatus==='approved'
        ?'Pagamento aprovado. Confirmando a transação…'
        :'Pagamento pendente. Aguardando a confirmação do Mercado Pago…');
      try{
        await generatePreview({scroll:false});
        const paidAccess=await waitForPaidAccess(requested);
        const offer=paidAccess.offer;
        if(!offer.allowed){
          showExport(offer);
          checkoutMsg('O pagamento ainda está sendo confirmado. Clique em “Já paguei · atualizar acesso” para verificar novamente.');
          return;
        }
        if(paidAccess.purchase){
          const generation=await waitForServerGeneration(requested,offer);
          if(generation.mode==='ready')clearPendingExport(requested);
        }else{
          await exportPaidDocuments(offer);
          clearPendingExport(requested);
        }
        window.history.replaceState({},'', '/criar-documentos?application_id='+encodeURIComponent(requested));
      }catch(error){
        checkoutMsg(error.message||'Não foi possível concluir a geração automática.');
      }
    }
    let applicationLookupRequest=0;
    function setApplicationListState({loading=false,message='',error=false,retry=false}={}){
      $('applicationPicker').setAttribute('aria-busy',String(loading));
      $('applicationsLoading').hidden=!loading;
      $('applicationsLoading').setAttribute('aria-busy',String(loading));
      $('applicationsMessage').textContent=message;
      $('applicationsMessage').className='lookup-message'+(error?' lookup-error':'');
      $('retryApplications').hidden=!retry;
    }
    function setApplicationLookupState({loading=false,message='',error=false,retry=false}={}){
      $('applicationLookup').setAttribute('aria-busy',String(loading));
      $('applicationLookupLoading').hidden=!loading;
      $('applicationLookupLoading').setAttribute('aria-busy',String(loading));
      $('applicationHint').hidden=loading;
      $('applicationHint').textContent=message;
      $('applicationHint').classList.toggle('lookup-error',error);
      $('retryApplication').hidden=!retry;
    }
    async function loadApplications(){
      setApplicationListState({loading:true});
      try{
        const r=await fetch('/applications');
        if(!r.ok)throw new Error('Não foi possível carregar suas candidaturas.');
        const data=await r.json();
        const select=$('applicationSelect');
        select.querySelectorAll('option:not(:first-child)').forEach(option=>option.remove());
        const applications=data.applications||[];
        applications.forEach(item=>{
          const option=document.createElement('option');
          option.value=item.id;
          option.textContent=(item.job_title||'Cargo sem título')+' · '+(item.company||'Empresa não informada')+' · '+(item.status||'Identificada');
          select.appendChild(option);
        });
        setApplicationListState({message:applications.length?'':'Ainda não há candidaturas captadas. Você pode preencher os dados manualmente.'});
        const requestedFromUrl=new URLSearchParams(window.location.search).get('application_id');
        const requested=requestedFromUrl||readPendingExport();
        if(requested){
          select.value=requested;
          if(await selectApplication(requested)){
            if(requestedFromUrl){
              await handlePaymentReturn();
            }else{
              const restored=await restorePaidApplication();
              if(restored)msg('Retomamos a candidatura que aguardava confirmação do pagamento.',true);
            }
            if(paramsAutoPrepare()&&!new URLSearchParams(window.location.search).has('payment_status')){
              try{
                await generatePreview();
                window.history.replaceState({},'','/criar-documentos?application_id='+encodeURIComponent(requested));
              }catch(error){msg(error.message||'Não foi possível preparar a candidatura. Você pode tentar gerar a prévia novamente.')}
            }
          }
        }
      }catch{
        setApplicationListState({message:'Não foi possível carregar suas candidaturas. Você pode preencher manualmente ou tentar novamente.',error:true,retry:true});
      }
    }
    function paramsAutoPrepare(){return new URLSearchParams(window.location.search).get('auto_prepare')==='1'}
    async function selectApplication(id){
      const request=++applicationLookupRequest;
      linkedApplicationId=id?Number(id):null;
      current=null;
      if(!linkedApplicationId||!Number.isFinite(linkedApplicationId)){
        linkedApplicationId=null;
        setApplicationLookupState({message:'Preencha os campos manualmente ou escolha uma candidatura captada.'});
        return false;
      }
      setApplicationLookupState({loading:true});
      try{
        const appResponse=await fetch(`/applications/${linkedApplicationId}`);
        if(!appResponse.ok)throw new Error('Não foi possível carregar a candidatura selecionada.');
        const application=await appResponse.json();
        const r=await fetch(`/jobs/${application.job_id}`);
        if(!r.ok)throw new Error('Não foi possível carregar a vaga selecionada.');
        const data=await r.json();
        if(Number(data.application_id)!==linkedApplicationId)throw new Error('A vaga selecionada ainda não possui candidatura.');
        if(request!==applicationLookupRequest)return false;
        $('title').value=data.title||'';
        $('company').value=data.company||'';
        $('location').value=[data.location,data.modality].filter(Boolean).join(' · ');
        $('url').value=data.url||'';
        $('details').value=data.description||'';
        setApplicationLookupState({message:'Vaga captada vinculada. Você pode revisar os campos antes de gerar.'});
        msg('Vaga captada carregada no estúdio.',true);
        return true;
      }catch(error){
        if(request!==applicationLookupRequest)return false;
        linkedApplicationId=null;
        setApplicationLookupState({message:error.message||'Não foi possível carregar esta vaga.',error:true,retry:true});
        return false;
      }
    }
    async function generatePreview({scroll=true}={}){
      const button=$('generate');
      button.disabled=true;
      button.classList.add('busy');
      button.setAttribute('aria-busy','true');
      button.textContent='Gerando prévia...';
      msg('Adaptando seu currículo e escrevendo a carta…');
      try{
        const r=await fetch('/document-studio/generate',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            application_id:linkedApplicationId,
            title:$('title').value.trim(),
            company:$('company').value.trim(),
            location:$('location').value.trim(),
            url:$('url').value.trim(),
            details:$('details').value.trim()
          })
        });
        const data=await r.json();
        if(!r.ok)throw new Error(data.detail||'Não foi possível gerar a prévia.');
        current=data;
        renderQuickCopy(data.quick_copy);
        $('resultSubtitle').textContent=data.company+' · '+data.job_title;
        $('score').textContent=(data.analysis&&data.analysis.score!=null?data.analysis.score:'—')+'% de aderência';
        $('resumeSummary').textContent=(data.resume_preview&&data.resume_preview.name||'Candidato')+'\n'
          +(data.resume_preview&&(data.resume_preview.headline||data.resume_preview.target)||data.job_title)+'\n\n'
          +(data.resume_preview&&data.resume_preview.summary||'')+'\n\nExperiências adaptadas:\n'
          +((data.resume_preview&&data.resume_preview.experiences||[]).map(x=>'• '+x.role+' · '+x.company).join('\n')||'• Seu histórico será organizado aqui');
        $('skills').innerHTML=((data.resume_preview&&data.resume_preview.skills)||[]).map(x=>'<span class="skill">'+x.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</span>').join('');
        $('letter').textContent=data.cover_letter_preview||'A carta personalizada aparecerá aqui.';
        $('result').classList.add('visible');
        showExport(data.export);
        msg(data.linked_application?'Prévia gerada a partir da vaga captada.':'Prévia gerada com sucesso.',true);
        if(scroll)$('result').scrollIntoView({behavior:'smooth',block:'start'});
        return data;
      }finally{
        button.disabled=false;
        button.classList.remove('busy');
        button.removeAttribute('aria-busy');
        button.textContent='Gerar minha prévia personalizada';
      }
    }
    $('applicationSelect').addEventListener('change',async e=>{
      if(!await selectApplication(e.target.value))return;
      try{await restorePaidApplication()}catch(error){checkoutMsg(error.message||'Não foi possível restaurar os documentos pagos.')}
    });
    $('retryApplications').addEventListener('click',loadApplications);
    $('retryApplication').addEventListener('click',async()=>{
      if(await selectApplication($('applicationSelect').value)){
        try{await restorePaidApplication()}catch(error){checkoutMsg(error.message||'Não foi possível restaurar os documentos pagos.')}
      }
    });
    $('studioForm').addEventListener('submit',async e=>{
      e.preventDefault();
      try{await generatePreview()}catch(error){msg(error.message||'Não foi possível gerar a prévia.')}
    });
    $('clear').addEventListener('click',()=>{
      const hasDraft=['title','company','location','url','details'].some(id=>$(id).value.trim())||current!==null||$('result').classList.contains('visible');
      if(hasDraft&&!window.confirm('Limpar os dados preenchidos e a prévia gerada?'))return;
      $('studioForm').reset();
      $('result').classList.remove('visible');
      $('exportActions').hidden=true;
      current=null;
      linkedApplicationId=null;
      applicationLookupRequest++;
      setApplicationLookupState({message:'Preencha os campos manualmente ou escolha uma candidatura captada.'});
      msg('');
      $('title').focus();
    });
    $('checkout').addEventListener('click',async()=>{
      const b=$('checkout');
      b.disabled=true;
      b.textContent='Abrindo pagamento…';
      checkoutMsg('');
      const paymentWindow=window.open('about:blank','_blank');
      try{
        if(!current||!current.application_id)throw new Error('Gere a prévia antes de liberar o download.');
        const r=await fetch('/billing/document-export/checkout',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({application_id:current.application_id})
        });
        const d=await r.json();
        if(!r.ok)throw new Error(d.detail||'Não foi possível abrir o pagamento.');
        if(paymentWindow){
          savePendingExport(current.application_id);
          paymentWindow.location.href=d.checkout_url;
          paymentWindow.focus&&paymentWindow.focus();
          checkoutMsg('Checkout Mercado Pago aberto em outra aba. O Pix aparece entre os métodos disponíveis da sua conta.',true);
          b.textContent='Pagamento aberto em outra aba';
        }else{
          checkoutMsg('O navegador bloqueou a nova aba. Clique novamente para abrir o checkout.');
          b.textContent='Abrir pagamento';
          b.disabled=false;
        }
      }catch(error){
        if(paymentWindow)paymentWindow.close();
        checkoutMsg(error.message);
        msg(error.message);
        b.textContent='Liberar currículo + carta';
        b.disabled=false;
      }
    });
    $('refreshAccess').addEventListener('click',refreshAccess);
    $('retryGeneration').addEventListener('click',async()=>{
      try{
        $('retryGeneration').disabled=true;
        checkoutMsg('Solicitando uma nova tentativa de geração…');
        const offer=await getOffer();
        await exportPaidDocuments(offer);
      }catch(error){checkoutMsg(error.message||'Não foi possível solicitar nova tentativa.');}
      finally{$('retryGeneration').disabled=false;}
    });
    $('downloadResume').addEventListener('click',()=>{
      const url=$('downloadResume').dataset.url||(current&&current.application_id?'/applications/'+current.application_id+'/document':'');
      if(url)window.location.href=url;
    });
    $('downloadLetter').addEventListener('click',()=>{
      const url=$('downloadLetter').dataset.url||(current&&current.application_id?'/applications/'+current.application_id+'/cover-letter/document':'');
      if(url)window.location.href=url;
    });
    $('downloadResumePdf').addEventListener('click',()=>{const url=$('downloadResumePdf').dataset.url;if(url)window.location.href=url});
    $('downloadLetterPdf').addEventListener('click',()=>{const url=$('downloadLetterPdf').dataset.url;if(url)window.location.href=url});
    $('emailRecipient').addEventListener('change',()=>{$('emailConsent').checked=false;updateEmailSubmissionControls()});
    $('emailBody').addEventListener('input',updateEmailSubmissionControls);
    $('emailConsent').addEventListener('change',updateEmailSubmissionControls);
    $('refreshEmailPreview').addEventListener('click',loadEmailSubmissionPreview);
    $('sendEmailApplication').addEventListener('click',sendReviewedEmailApplication);
    document.addEventListener('visibilitychange',()=>{
      if(document.visibilityState==='visible')restorePendingCheckoutOnFocus();
    });
    window.addEventListener('focus',restorePendingCheckoutOnFocus);
    loadApplications();
