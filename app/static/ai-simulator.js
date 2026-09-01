(function () {
  const qs = Array.from(document.querySelectorAll('.question'));
  const next = document.querySelector('#next');
  if (!next || !qs.length) return;
  let i = 0;
  const answers = [];
  const local = (text) => {
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    if (words < 5) return { score: 0, title: 'Resposta insuficiente', msg: 'Escreva pelo menos uma ideia completa com contexto.' };
    let score = 45;
    if (words >= 25) score += 15;
    if (words >= 55) score += 10;
    if (/(exemplo|projeto|empresa|equipe|situação|problema|resultado|liderei)/i.test(text)) score += 10;
    if (/\d|%|reduz|aument|entreg|impact|resultado|prazo/i.test(text)) score += 12;
    if (/(vaga|cargo|empresa|posição|oportunidade|contribu)/i.test(text)) score += 8;
    return { score, title: score >= 80 ? 'Resposta consistente' : score >= 60 ? 'Pode ser fortalecida' : 'Resposta genérica', msg: score >= 80 ? 'Boa estrutura, evidências e conexão com a oportunidade.' : 'Inclua situação, ação e resultado mensurável.' };
  };
  const paint = (q, r) => { const b = q.querySelector('.feedback'); b.className = 'feedback show ' + (r.score >= 80 ? 'good' : r.score >= 60 ? 'warn' : 'bad'); b.innerHTML = '<strong>' + r.title + ' · ' + r.score + '/100</strong>' + (r.msg || '') + (r.strengths?.length ? '<br><br><b>Pontos fortes:</b> ' + r.strengths.join(' · ') : '') + (r.improvements?.length ? '<br><b>Melhore:</b> ' + r.improvements.join(' · ') : '') + (r.rewritten ? '<br><br><b>Versão sugerida:</b> ' + r.rewritten : ''); };
  const render = () => { qs.forEach((q, n) => q.classList.toggle('active', n === i)); const bar = document.querySelector('#bar'); if (bar) bar.style.width = ((i + 1) / qs.length * 100) + '%'; const back = document.querySelector('#back'); if (back) back.hidden = i === 0; };
  const ask = async (q, text) => { try { const res = await fetch('/api/interviews/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q.querySelector('h2').textContent, answer: text }) }); if (res.ok) return await res.json(); } catch (_) {} return local(text); };
  const finish = () => { document.querySelector('#session').style.display = 'none'; const out = document.querySelector('#result'); out.classList.add('show'); const avg = Math.round(answers.reduce((a, r) => a + r.score, 0) / answers.length); document.querySelector('#score').textContent = avg; document.querySelector('#rows').innerHTML = answers.map((r, n) => '<div class="result-row"><strong>' + qs[n].dataset.title + ' — ' + r.score + '/100</strong><span>' + (r.msg || r.title) + '</span></div>').join(''); const note = out.querySelector('.note'); if (note) note.textContent = answers.some(r => r.provider) ? 'Análise feita pela mini IA Gemini, hospedada com segurança no backend.' : 'Análise estruturada disponível. A mini IA será usada quando a chave estiver ativa no Render.'; };
  document.addEventListener('click', async (ev) => { if (ev.target !== next) return; ev.preventDefault(); ev.stopImmediatePropagation(); const q = qs[i], text = q.querySelector('textarea').value.trim(); next.disabled = true; next.textContent = 'Analisando…'; const r = await ask(q, text); paint(q, r); next.disabled = false; next.textContent = 'Avaliar resposta →'; if (!r.score) return; answers[i] = r; if (i === qs.length - 1) return finish(); i += 1; render(); }, true);
})();
