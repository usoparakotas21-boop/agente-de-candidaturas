"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

const html = fs.readFileSync("app/static/dashboard.html", "utf8");
const stateSource = html.match(/\/\/ GUIDED_ONBOARDING_STATE_BEGIN([\s\S]*?)\/\/ GUIDED_ONBOARDING_STATE_END/);
assert.ok(stateSource, "onboarding state helper is embedded in the dashboard shell");
const onboardingLogic = html.slice(html.indexOf("function dismissGuidedOnboarding"), html.indexOf("function populateStatusOptions"));
const handlersStart = html.indexOf('$("closeGuidedOnboarding")');
const handlersEnd = html.indexOf('$("showLoginTab")', handlersStart);
const onboardingHandlers = html.slice(handlersStart, handlersEnd);
const browserWindow = {};
vm.runInNewContext(stateSource[1], { window: browserWindow });
const { create, keyForUser } = browserWindow.GuidedOnboardingState;

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    keys: () => [...values.keys()],
  };
}

test("the onboarding key is namespaced by authenticated account id", () => {
  assert.equal(keyForUser("user-123"), "ac_guided_onboarding_v1:user-123");
  assert.equal(keyForUser(""), "");
  assert.notEqual(keyForUser("user-123"), keyForUser("user-456"));
});

test("saving the next step pauses and survives a new dashboard session", () => {
  const storage = memoryStorage();
  const firstVisit = create(storage, "account-a");
  assert.equal(firstVisit.shouldShow(false, false), true);
  assert.equal(firstVisit.saveStep(1), true);

  const returnedDashboard = create(storage, "account-a");
  assert.deepEqual({ ...returnedDashboard.read() }, { step: 1, started: true, completed: false });
  assert.equal(returnedDashboard.shouldShow(true, true), true);
});

test("progress for one account is isolated from another account on the same browser", () => {
  const storage = memoryStorage();
  create(storage, "account-a").saveStep(2);

  const otherAccount = create(storage, "account-b");
  assert.deepEqual({ ...otherAccount.read() }, { step: 0, started: false, completed: false });
  assert.equal(otherAccount.shouldShow(true, true), false);
  assert.equal(storage.keys().length, 1);
});

test("only explicit completion persists a permanent dismissal", () => {
  const storage = memoryStorage();
  const state = create(storage, "account-a");
  state.saveStep(2);
  assert.equal(state.shouldShow(true, true), true);

  state.complete();
  const nextVisit = create(storage, "account-a");
  assert.deepEqual({ ...nextVisit.read() }, { step: 2, started: true, completed: true });
  assert.equal(nextVisit.shouldShow(false, false), false);
  assert.equal(nextVisit.saveStep(1), false);
});

test("invalid or unavailable storage never creates a shared global completion", () => {
  assert.equal(create(memoryStorage(), null).complete(), false);
  const deniedStorage = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };
  const state = create(deniedStorage, "account-a");
  assert.equal(state.shouldShow(false, false), true);
  assert.equal(state.saveStep(99), false);
  assert.equal(state.complete(), false);
});

test("dashboard actions pause for work and only close or skip can complete the guide", () => {
  assert.match(html, /data-guided-link data-guided-next-step="1" href="\/curriculos"/);
  assert.match(html, /data-guided-link data-guided-next-step="2" href="\/configuracoes#preferencias"/);
  assert.match(onboardingHandlers, /if \(Number\.isInteger\(nextStep\)\) pauseGuidedOnboarding\(nextStep, false\)/);
  assert.match(onboardingHandlers, /guidedCaptureButton"\)\.addEventListener\("click", \(\) => \{\s*guidedOnboardingTrigger = \$\("captureJobButton"\);\s*pauseGuidedOnboarding\(guidedOnboardingStep, false\)/);
  assert.match(onboardingHandlers, /closeGuidedOnboarding"\)\.addEventListener\("click", dismissGuidedOnboarding\)/);
  assert.match(onboardingHandlers, /skipGuidedOnboarding"\)\.addEventListener\("click", dismissGuidedOnboarding\)/);
  assert.match(html, /if \(event\.persisted && !\$\("appShell"\)\.hidden\) syncOnboardingCard\(\)/);
  assert.match(onboardingLogic, /\$\("guidedNextButton"\)\.textContent = guidedOnboardingStep === 2 \? "Fechar por enquanto"/);
});
