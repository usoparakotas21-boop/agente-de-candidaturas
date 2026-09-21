const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createFillPlan } = require("../chrome-extension/field-filler.js");

const profile = {
  name: "Ana Beatriz Souza",
  email: "ana@example.com",
  phone: "+55 71 99999-0000",
  linkedin: "https://linkedin.com/in/anabeatriz",
  location: "Salvador, BA",
  headline: "Analista de Recursos Humanos",
  summary: "Profissional de RH com experiência em seleção.",
  experiences: [{ role: "Analista de RH", company: "Empresa Alfa", period: "2022 — 2025", description: "Recrutamento e seleção." }],
  education: [{ course: "Administração", institution: "Universidade Beta", period: "2018 — 2022" }],
  skills: ["Recrutamento", "Excel"],
  languages: ["Português"]
};

test("preenche campos vazios identificados por rótulos e autocomplete", () => {
  const descriptors = [
    { tagName: "input", type: "text", autocomplete: "given-name", visible: true },
    { tagName: "input", type: "text", label: "Sobrenome", visible: true },
    { tagName: "input", type: "email", label: "E-mail", visible: true },
    { tagName: "textarea", type: "textarea", label: "Experiência profissional", visible: true },
    { tagName: "textarea", type: "textarea", label: "Competências", visible: true }
  ];
  const plan = createFillPlan(descriptors, profile);
  assert.deepEqual(plan.map(item => item.key), ["first_name", "last_name", "email", "experiences", "skills"]);
  assert.equal(plan[0].value, "Ana");
  assert.equal(plan[1].value, "Beatriz Souza");
  assert.match(plan[3].value, /Empresa Alfa/);
});

test("preenche cidade e estado apenas quando há uma opção exata no seletor", () => {
  const descriptors = [
    { tagName: "select", type: "select-one", label: "Cidade", options: [{ value: "", text: "Selecione", disabled: false }, { value: "salvador", text: "Salvador", disabled: false }, { value: "santos", text: "Salvador", disabled: true }], visible: true },
    { tagName: "select", type: "select-one", label: "Estado", options: [{ value: "", text: "Selecione", disabled: false }, { value: "bahia", text: "Bahia", disabled: false }], visible: true },
    { tagName: "select", type: "select-one", label: "Estado de nascimento", options: [{ value: "BA", text: "Bahia", disabled: false }], visible: true },
    { tagName: "select", type: "select-one", label: "Cidade", options: [{ value: "", text: "Selecione", disabled: false }, { value: "feira", text: "Feira de Santana", disabled: false }], visible: true }
  ];
  const plan = createFillPlan(descriptors, profile);
  assert.deepEqual(plan, [
    { index: 0, key: "city", value: "salvador" },
    { index: 1, key: "state", value: "bahia" }
  ]);
});

test("ignora campos preenchidos, ocultos, senhas, upload e respostas sensíveis", () => {
  const descriptors = [
    { tagName: "input", type: "text", label: "Nome completo", hasValue: true, visible: true },
    { tagName: "input", type: "password", autocomplete: "current-password", visible: true },
    { tagName: "input", type: "file", label: "Currículo", visible: true },
    { tagName: "input", type: "text", label: "Por que deseja trabalhar aqui?", visible: true },
    { tagName: "input", type: "text", label: "E-mail", visible: false },
    { tagName: "input", type: "text", label: "Aceito os termos", visible: true }
  ];
  assert.deepEqual(createFillPlan(descriptors, profile), []);
});

test("não preenche endereço, vaga pretendida, consentimento ou captcha por aproximação", () => {
  const descriptors = [
    { tagName: "input", type: "text", name: "street_address", label: "Endereço", visible: true },
    { tagName: "input", type: "text", name: "desired_position", label: "Cargo desejado", visible: true },
    { tagName: "input", type: "text", name: "captcha", label: "Captcha", visible: true },
    { tagName: "input", type: "checkbox", label: "E-mail", visible: true },
    { tagName: "textarea", type: "textarea", label: "I accept the terms and conditions", visible: true }
  ];
  assert.deepEqual(createFillPlan(descriptors, profile), []);
});

test("não corta silenciosamente respostas para caber no limite do portal", () => {
  const descriptors = [
    { tagName: "textarea", type: "textarea", label: "Resumo profissional", maxLength: 20, visible: true }
  ];
  assert.deepEqual(createFillPlan(descriptors, profile), []);
});

test("complemento não pede acesso permanente a sites nem dispara envio ou rede", () => {
  const root = path.resolve(__dirname, "../chrome-extension");
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
  const filler = fs.readFileSync(path.join(root, "field-filler.js"), "utf8");
  const popup = fs.readFileSync(path.join(root, "popup.js"), "utf8");
  const popupHtml = fs.readFileSync(path.join(root, "popup.html"), "utf8");
  assert.deepEqual(manifest.permissions.sort(), ["activeTab", "scripting", "storage"]);
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.doesNotMatch(filler, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
  assert.doesNotMatch(popup, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit/);
  assert.match(popupHtml, /Confirmei que este portal permite preenchimento assistido/);
  assert.ok(popup.includes("https:"));
  assert.ok(!popup.includes("https?:"));
  assert.match(popupHtml, /vou revisar tudo antes de enviar/i);
});
