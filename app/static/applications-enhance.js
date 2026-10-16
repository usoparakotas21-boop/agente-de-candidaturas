(function () {
  const list = document.querySelector('#list');
  if (!list) return;
  const labels = {IDENTIFICADA:'Identificada',ANALISADA:'Analisada',PERSONALIZADA:'Personalizada',CURRICULO_GERADO:'Currículo gerado',CANDIDATURA_ENVIADA:'Enviada',ENTREVISTA:'Entrevista',APROVADO:'Aprovada',RECUSADO:'Recusada',ARQUIVADA:'Arquivada'};
  let apps = [];
  function span(value, marker = false) {
    const node = document.createElement('span');
    if (marker) node.appendChild(document.createElement('i'));
    node.appendChild(document.createTextNode(String(value)));
    return node;
  }
  function enhance() {
    list.querySelectorAll('.item').forEach(item => {
      if (item.dataset.enhanced) return;
      const title = item.querySelector('h2')?.textContent || '', a = apps.find(x => x.job_title === title);
      if (!a) return;
      item.dataset.enhanced = '1';
      const meta = item.querySelector('.meta');
      const analysis = a.analysis_score == null ? 'Score pendente' : 'Análise: ' + Math.round(a.analysis_score) + '%';
      const vacancy = ['RECUSADO','ARQUIVADA'].includes(a.status) ? 'Vaga encerrada' : 'Vaga aberta';
      meta.replaceChildren(span(a.company || 'Empresa não informada'), span(analysis), span(vacancy));
      const timeline = document.createElement('div');
      timeline.className = 'mini-timeline';
      const events = (a.events || []).slice(-4);
      timeline.replaceChildren(...(events.length
        ? events.map(e => span(labels[e.status] || e.status, true))
        : [span('Oportunidade capturada', true)]));
      item.appendChild(timeline);
    });
  }
  fetch('/applications').then(r => r.json()).then(d => { apps = d.applications || []; enhance(); }).catch(() => {});
  new MutationObserver(enhance).observe(list, {childList:true});
})();
