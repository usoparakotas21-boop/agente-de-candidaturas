/* Shared plan indicator and expiration notice for authenticated screens. */
(() => {
  const ensureStyles = () => {
    if (document.getElementById('planStatusStyles')) return;
    const style = document.createElement('style');
    style.id = 'planStatusStyles';
    style.textContent = '.plan-expiry-alert{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:12px auto 0;width:min(1160px,calc(100% - 32px));padding:11px 15px;border:1px solid #f4c95d;border-radius:12px;background:#fff8df;color:#704f00;font:600 13px Inter,system-ui,sans-serif}.plan-expiry-alert[data-state="danger"]{border-color:#fca5a5;background:#fff1f2;color:#991b1b}.plan-expiry-alert a{color:inherit;font-weight:850;text-decoration:underline;white-space:nowrap}@media(max-width:650px){.plan-expiry-alert{align-items:flex-start;flex-direction:column;gap:7px;width:calc(100% - 24px)}}';
    document.head.appendChild(style);
  };
  const formatDate = value => {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('pt-BR');
  };
  const setBadge = data => {
    const badge = document.getElementById('globalPlanBadge') || (() => {
      const topbar = document.querySelector('.topbar');
      if (!topbar) return null;
      const target = topbar.querySelector('.user-controls') || topbar;
      const el = document.createElement('span');
      el.id = 'globalPlanBadge';
      el.className = 'global-plan-badge';
      el.style.cssText = 'display:inline-flex;align-items:center;margin-left:10px;padding:5px 9px;border-radius:999px;background:#edf3ff;color:#1a3e82;font:800 11px Inter,system-ui,sans-serif;white-space:nowrap';
      target.prepend(el);
      return el;
    })();
    if (!badge) return;
    const name = data.plan_name || 'Essencial';
    badge.textContent = `Plano: ${name}`;
    badge.dataset.state = data.alert_state || 'ok';
    badge.title = data.access_until ? `Acesso até ${formatDate(data.access_until)}` : 'Plano atual';
  };
  const showAlert = data => {
    const existing = document.getElementById('planExpiryAlert');
    if (existing) existing.remove();
    if (!data || !data.alert_message) return;
    ensureStyles();
    const alert = document.createElement('div');
    alert.id = 'planExpiryAlert';
    alert.className = 'plan-expiry-alert';
    alert.dataset.state = data.alert_state || 'warning';
    const message = document.createElement('span');
    message.textContent = data.alert_message;
    const link = document.createElement('a');
    link.href = '/configuracoes#plan';
    link.textContent = data.status === 'canceled' ? 'Ver opções de renovação' : 'Ver plano e cobrança';
    alert.append(message, link);
    const topbar = document.querySelector('.topbar');
    const nav = document.querySelector('.global-nav');
    (topbar || nav || document.body).insertAdjacentElement('afterend', alert);
  };
  const load = async () => {
    try {
      const response = await fetch('/billing/subscription', {credentials: 'same-origin'});
      if (!response.ok) return;
      const data = await response.json();
      const until = data.access_until ? new Date(data.access_until) : null;
      const now = Date.now();
      const days = until && !Number.isNaN(until.getTime()) ? Math.ceil((until.getTime() - now) / 86400000) : null;
      data.alert_state = days !== null && days <= 2 ? 'danger' : (days !== null && days <= 7 ? 'warning' : 'ok');
      if (days !== null && days <= 0) data.alert_message = `O acesso do plano ${data.plan_name || ''} terminou${formatDate(data.access_until) ? ` em ${formatDate(data.access_until)}` : ''}.`;
      else if (days !== null && days <= 7) data.alert_message = `Seu plano ${data.plan_name || ''} vence em ${days <= 1 ? 'menos de 1 dia' : `${days} dias`} (${formatDate(data.access_until)}).`;
      else if (data.status === 'pending') data.alert_message = 'Seu pagamento está aguardando confirmação. Os recursos pagos serão liberados assim que o Mercado Pago confirmar.';
      else if (data.status === 'canceled' && data.active) data.alert_message = `A renovação foi cancelada; seu acesso continua até ${formatDate(data.access_until) || 'o fim do período pago'}.`;
      else data.alert_message = '';
      setBadge(data);
      showAlert(data);
    } catch (_) {
      // The plan indicator is progressive enhancement and must never block the page.
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load, {once: true});
  else load();
})();
