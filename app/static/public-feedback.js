(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const list = document.getElementById('feedbackList');
  const landingGrid = document.getElementById('publicFeedbackGrid');
  const rating = document.getElementById('rating');
  let selectedRating = 5;

  function paintRating() {
    rating?.querySelectorAll('[data-rating]').forEach(button => {
      button.classList.toggle('active', Number(button.dataset.rating) <= selectedRating);
    });
  }
  rating?.addEventListener('click', event => {
    const button = event.target.closest('[data-rating]');
    if (!button) return;
    selectedRating = Number(button.dataset.rating) || 5;
    paintRating();
  });
  paintRating();

  async function load() {
    if (!list && !landingGrid) return;
    try {
      const response = await fetch('/api/feedback/public', {credentials: 'same-origin'});
      const data = await response.json();
      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) {
        if (list) list.innerHTML = '<div class="empty">Ainda estamos reunindo os primeiros relatos. Seja a primeira pessoa a contribuir.</div>';
        return;
      }
      const cards = items.map(item => {
        const stars = '★'.repeat(Math.max(1, Math.min(5, Number(item.rating) || 5)));
        return {item, stars, feedback: `<article class="item"><div class="item-head"><div><h3>${esc(item.title)}</h3><div class="meta">${esc(item.display_name)} · ${esc(item.category)}</div></div><span class="rating" aria-label="${Number(item.rating) || 5} de 5">${stars}</span></div><p>${esc(item.message)}</p></article>`, card: `<div class="testimonial-card"><p class="testimonial-text">${esc(item.message)}</p><div class="testimonial-author"><div class="testimonial-avatar" style="background:#eef2f8;color:var(--blue)">${esc((item.display_name || 'P').slice(0,1).toUpperCase())}</div><div class="testimonial-info"><strong>${esc(item.display_name)}</strong><span>${esc(item.title)}</span></div></div></div>`};
      });
      if (list) list.innerHTML = cards.map(card => card.feedback).join('');
      if (landingGrid) landingGrid.innerHTML = cards.slice(0, 3).map(card => card.card).join('');
    } catch {
      list.innerHTML = '<div class="empty">Não foi possível carregar os relatos agora.</div>';
    }
  }

  const form = document.getElementById('feedbackForm');
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = document.getElementById('feedbackSubmit');
    const status = document.getElementById('feedbackStatus');
    button.disabled = true;
    status.className = 'status';
    status.textContent = 'Enviando…';
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          title: document.getElementById('feedbackTitle').value.trim(),
          message: document.getElementById('feedbackMessage').value.trim(),
          category: document.getElementById('feedbackCategory').value,
          display_name: document.getElementById('feedbackName').value.trim(),
          rating: selectedRating,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Não foi possível enviar o feedback.');
      status.className = 'status ok';
      status.textContent = data.message || 'Feedback enviado para revisão.';
      form.reset();
      selectedRating = 5;
      paintRating();
    } catch (error) {
      status.className = 'status error';
      status.textContent = error.message || 'Não foi possível enviar o feedback.';
    } finally {
      button.disabled = false;
    }
  });
  load();
})();
