"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync("app/static/ai-simulator.js", "utf8");

class Element {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.maxLength = 0;
    this.dataset = {};
    this.listeners = new Map();
    this.children = [];
    this.classList = {
      add: name => { if (!this.className.split(/\s+/).includes(name)) this.className = `${this.className} ${name}`.trim(); },
      remove: name => { this.className = this.className.split(/\s+/).filter(value => value && value !== name).join(" "); },
      toggle: (name, force) => {
        const enabled = force ?? !this.className.split(/\s+/).includes(name);
        if (enabled) this.classList.add(name);
        else this.classList.remove(name);
        return enabled;
      },
      contains: name => this.className.split(/\s+/).includes(name),
    };
  }

  addEventListener(type, handler) {
    const handlers = this.listeners.get(type) || [];
    handlers.push(handler);
    this.listeners.set(type, handlers);
  }

  insertAdjacentElement(_position, element) { this.children.push(element); }
  replaceChildren(...children) { this.children = children; this.innerHTML = ""; }
  querySelector(selector) { return this.selectors?.get(selector) || null; }
}

function createHarness() {
  const questions = Array.from({length: 5}, (_, index) => {
    const question = new Element(`question-${index}`);
    const heading = new Element("heading");
    heading.textContent = `Pergunta ${index + 1}`;
    const textarea = new Element("textarea");
    const feedback = new Element("feedback");
    question.dataset.title = `pergunta ${index + 1}`;
    question.selectors = new Map([["h2", heading], ["textarea", textarea], [".feedback", feedback]]);
    return question;
  });
  const ids = new Map(["next", "back", "restart", "bar", "session", "result", "score", "rows"].map(id => [id, new Element(id)]));
  const note = new Element("note");
  ids.get("result").selectors = new Map([[".note", note]]);
  const documentListeners = new Map();
  const windowListeners = new Map();
  const document = {
    querySelectorAll: selector => selector === ".question" ? questions : [],
    querySelector: selector => ids.get(selector.replace(/^#/, "")) || null,
    createElement: () => new Element("created"),
    addEventListener: (type, handler) => documentListeners.set(type, handler),
  };
  const window = {
    addEventListener: (type, handler) => windowListeners.set(type, handler),
    dispatchEvent: event => windowListeners.get(event.type)?.(event),
  };
  const context = {
    document,
    window,
    fetch: async () => ({ok: false, status: 402, json: async () => ({detail: {code: "PRO_PLAN_REQUIRED"}})}),
  };
  vm.runInNewContext(source, context);
  return {questions, ids, note, documentListeners, window};
}

const answer = "Na equipe de recrutamento e seleção, organizei os dados e reduzi o prazo em 20%.";

test("refazer a simulação reinicia índice, feedback, respostas e resultado", async () => {
  const {questions, ids, documentListeners} = createHarness();
  for (let index = 0; index < questions.length; index += 1) {
    questions[index].querySelector("textarea").value = answer;
    await documentListeners.get("click")({target: ids.get("next"), preventDefault() {}, stopImmediatePropagation() {}});
  }

  assert.equal(ids.get("result").classList.contains("show"), true);
  assert.equal(ids.get("session").classList.contains("is-hidden"), true);
  await ids.get("restart").listeners.get("click")[0]();

  assert.equal(ids.get("result").classList.contains("show"), false);
  assert.equal(ids.get("session").classList.contains("is-hidden"), false);
  assert.equal(ids.get("back").hidden, true);
  assert.equal(ids.get("bar").className, "progress-fill progress-step-1");
  assert.ok(questions.every(question => question.querySelector("textarea").value === ""));
  assert.ok(questions.every(question => question.querySelector(".feedback").className === "feedback"));

  questions[0].querySelector("textarea").value = answer;
  await documentListeners.get("click")({target: ids.get("next"), preventDefault() {}, stopImmediatePropagation() {}});
  assert.equal(questions[1].classList.contains("active"), true);
});

test("changing interview context resets scoring but preserves typed drafts", () => {
  const {questions, ids, window} = createHarness();
  questions[0].querySelector("textarea").value = answer;
  questions[0].querySelector(".feedback").className = "feedback show good";
  window.dispatchEvent({type: "interview:context-reset"});

  assert.equal(questions[0].querySelector("textarea").value, answer);
  assert.equal(questions[0].querySelector(".feedback").className, "feedback");
  assert.equal(ids.get("back").hidden, true);
  assert.equal(ids.get("result").classList.contains("show"), false);
  assert.equal(ids.get("bar").className, "progress-fill progress-step-1");
});
