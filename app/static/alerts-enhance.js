(function(){
  const section=document.querySelector('#alertas');
  if(!section)return;
  const interview=document.querySelector('#notifyInterviews');
  if(interview){
    const label=interview.closest('label');
    if(label){
      label.classList.add('critical');
      if(!label.querySelector('b')){
        const badge=document.createElement('b');
        badge.textContent='CRÍTICO';
        label.appendChild(badge);
      }
    }
  }
  const hint=document.querySelector('#notificationFrequency')?.closest('.notification-grid')?.querySelector('.hint');
  if(hint)hint.textContent='A frequência vale para avisos não críticos; entrevistas e follow-ups respeitam suas caixas acima.';
})();
