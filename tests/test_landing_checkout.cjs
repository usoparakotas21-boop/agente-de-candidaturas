const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(responses, pending) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', value: '', dataset: {}, handlers: {},
      classList: { toggle() {} }, focus() {}, showModal() {}, close() {},
      setAttribute() {}, removeAttribute() {},
      addEventListener(name, handler) { this.handlers[name] = handler; },
    });
    return elements.get(id);
  };
  const button = element('plan'); button.dataset.planCheckout = 'pro';
  const store = new Map();
  if (pending) store.set('ac_pending_plan_checkout', JSON.stringify({ plan: 'pro', expires_at: Date.now() + 60000 }));
  const location = { href: '', assign(url) { this.href = url; } };
  const calls = [];
  vm.runInNewContext(fs.readFileSync('app/static/landing-auth.js', 'utf8'), {
    document: { getElementById: element, querySelectorAll: selector => selector === '[data-plan-checkout]' ? [button] : [] },
    localStorage: { getItem: key => store.get(key), setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key) },
    location, window: {}, Date, console,
    fetch: async (...args) => { calls.push(args); const response = responses.shift(); return { ok: response.ok, json: async () => response.body || {} }; },
  });
  return { element, button, store, location, calls };
}

test('checkout failure displays the error and never redirects to a generic payment page', async () => {
  const state = setup([{ ok: true }, { ok: false, body: { detail: 'Pagamento indisponível' } }]);
  await state.button.handlers.click({ preventDefault() {} });
  assert.equal(state.element('landingLoginError').textContent, 'Pagamento indisponível');
  assert.equal(state.location.href, '');
});

test('pending checkout survives a provider failure after login', async () => {
  const state = setup([{ ok: true }, { ok: false, body: { detail: 'Tente novamente' } }], true);
  await state.element('landingLoginForm').handlers.submit({ preventDefault() {} });
  assert.equal(state.location.href, '');
  assert.ok(state.store.has('ac_pending_plan_checkout'));
  assert.equal(state.element('landingLoginError').textContent, 'Tente novamente');
});

test('successful pending checkout redirects to the provider and clears the pending plan', async () => {
  const url = 'https://www.mercadopago.com.br/subscriptions/checkout?id=test';
  const state = setup([{ ok: true }, { ok: true, body: { checkout_url: url } }], true);
  await state.element('landingLoginForm').handlers.submit({ preventDefault() {} });
  assert.equal(state.location.href, url);
  assert.equal(state.store.has('ac_pending_plan_checkout'), false);
  assert.equal(state.calls[1][0], '/billing/subscriptions/checkout');
});
