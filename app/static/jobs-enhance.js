(function(){
  const toolbar=document.querySelector('.toolbar'), list=document.querySelector('#list'); if(!toolbar||!list)return;
  const sort=document.createElement('select'); sort.id='sort'; sort.innerHTML='<option value="relevance">Ordenar: relevância</option><option value="date">Ordenar: mais recentes</option><option value="match">Ordenar: maior match</option>'; toolbar.appendChild(sort);
  const state={jobs:[]}; const saved=JSON.parse(localStorage.getItem('jobsFilters')||'{}'); if(saved.search)document.querySelector('#search').value=saved.search; if(saved.source)document.querySelector('#source').value=saved.source; if(saved.sort)sort.value=saved.sort;
  let enhancing=false;
  function enhance(){
    if(enhancing)return;
    enhancing=true;
    try {
      const cards=[...list.querySelectorAll('.job')];
      cards.forEach(c=>{const title=c.querySelector('h2')?.textContent||'',j=state.jobs.find(x=>(x.title||'')===title); if(j&&!c.querySelector('.match-badge')){const b=document.createElement('span');b.className='badge match-badge';const score=Number(j.match_score);if(j.match_score!=null&&Number.isFinite(score)){const rounded=Math.round(Math.max(0,Math.min(100,score)));b.classList.add(rounded>=75?'match-badge-positive':rounded>=50?'match-badge-attention':'match-badge-low');b.textContent=rounded+'% match';c.dataset.match=rounded;}else{b.classList.add('match-badge-pending');b.textContent='Match pendente';c.dataset.match=-1;}c.querySelector('.meta')?.appendChild(b);c.dataset.date=j.captured_at||'';} });
      const order=sort.value;
      const sorted=cards.slice().sort((a,b)=>order==='match'?Number(b.dataset.match)-Number(a.dataset.match):order==='date'?String(b.dataset.date).localeCompare(String(a.dataset.date)):0);
      if(sorted.some((card,index)=>card!==cards[index])) sorted.forEach(card=>list.appendChild(card));
    } finally { enhancing=false; }
  }
  ['search','source'].forEach(id=>document.querySelector('#'+id)?.addEventListener('input',()=>localStorage.setItem('jobsFilters',JSON.stringify({search:document.querySelector('#search').value,source:document.querySelector('#source').value,sort:sort.value}))));
  sort.addEventListener('change',()=>{localStorage.setItem('jobsFilters',JSON.stringify({search:document.querySelector('#search').value,source:document.querySelector('#source').value,sort:sort.value}));enhance()});
  fetch('/jobs').then(r=>r.json()).then(d=>{state.jobs=d.jobs||[];enhance()}).catch(()=>{});
  new MutationObserver(()=>{if(!enhancing)enhance()}).observe(list,{childList:true});
})();
