const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createFillPlan } = require("../chrome-extension/field-filler.js");
const { isRestrictedAutomationHost } = require("../chrome-extension/automation-policy.js");
const { classifyFileField, attachPdfsInPage } = require("../chrome-extension/pdf-attachment.js");

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

test("bloqueia portais que restringem automação e deixa o portal do empregador disponível", () => {
  assert.equal(isRestrictedAutomationHost("linkedin.com"), true);
  assert.equal(isRestrictedAutomationHost("www.linkedin.com"), true);
  assert.equal(isRestrictedAutomationHost("jobs.linkedin.cn"), true);
  assert.equal(isRestrictedAutomationHost("candidatos.jobbol.com.br"), true);
  assert.equal(isRestrictedAutomationHost("www.glassdoor.com"), true);
  assert.equal(isRestrictedAutomationHost("linkedin.com.example.org"), false);
  assert.equal(isRestrictedAutomationHost("glassdoor.com.example.org"), false);
  assert.equal(isRestrictedAutomationHost("careers.example.org"), false);
  const policy = require("../chrome-extension/automation-policy.js");
  assert.equal(policy.isSupportedAutomationHost("boards.greenhouse.io"), false);
  assert.equal(policy.isSupportedAutomationHost("careers.gupy.io"), true);
  assert.equal(policy.isSupportedAutomationHost("www.vagas.com.br"), true);
  assert.equal(policy.isSupportedAutomationHost("empregos.infojobs.com.br"), true);
  assert.equal(policy.isSupportedAutomationHost("gupy.io.example.org"), false);
});

test("só reconhece uploads explicitamente identificados como currículo ou carta", () => {
  assert.equal(classifyFileField({ labels: "Currículo em PDF" }), "resume");
  assert.equal(classifyFileField({ ariaLabel: "Upload resume" }), "resume");
  assert.equal(classifyFileField({ labels: "Carta de apresentação" }), "letter");
  assert.equal(classifyFileField({ name: "cover_letter_upload" }), "letter");
  assert.equal(classifyFileField({ labels: "Documento" }), null);
  assert.equal(classifyFileField({ labels: "Foto do perfil" }), null);
  assert.equal(classifyFileField({ labels: "Passaporte" }), null);
});

test("anexa PDF a um input oculto somente quando há rótulo visível e explícito", () => {
  const previous = {
    document: global.document,
    getComputedStyle: global.getComputedStyle,
    DataTransfer: global.DataTransfer,
    File: global.File,
  };
  try {
    const events = [];
    const label = { innerText: "Currículo em PDF", getClientRects: () => [1], style: { display: "block", visibility: "visible" } };
    const input = {
      accept: ".pdf", disabled: false, files: [], labels: [label], name: "resume", id: "resume-upload",
      title: "", closest: () => null, getClientRects: () => [],
      getAttribute: () => "", dispatchEvent: event => events.push(event.type),
    };
    global.document = { querySelectorAll: () => [input] };
    global.getComputedStyle = element => element.style || { display: "none", visibility: "hidden" };
    global.File = class File { constructor(parts, name, options) { this.parts = parts; this.name = name; this.type = options.type; } };
    global.DataTransfer = class DataTransfer {
      constructor() { this.entries = []; this.items = { add: file => this.entries.push(file) }; }
      get files() { return this.entries; }
    };
    const result = attachPdfsInPage({ resume: { name: "curriculo.pdf", base64: Buffer.from("%PDF-test").toString("base64") } });
    assert.equal(result.ok, true);
    assert.equal(input.files[0].name, "curriculo.pdf");
    assert.deepEqual(events, ["input", "change"]);
    input.labels = [];
    input.files = [];
    const unlabelled = attachPdfsInPage({ resume: { name: "curriculo.pdf", base64: Buffer.from("%PDF-test").toString("base64") } });
    assert.equal(unlabelled.ok, false);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete global[key];
      else global[key] = value;
    }
  }
});

test("complemento pede permissão do app só após clique e limita atuação à página ativa", () => {
  const root = path.resolve(__dirname, "../chrome-extension");
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
  const filler = fs.readFileSync(path.join(root, "field-filler.js"), "utf8");
  const popup = fs.readFileSync(path.join(root, "popup.js"), "utf8");
  const popupHtml = fs.readFileSync(path.join(root, "popup.html"), "utf8");
  const background = fs.readFileSync(path.join(root, "background.js"), "utf8");
  const widget = fs.readFileSync(path.join(root, "copilot-widget.js"), "utf8");
  const sidepanel = fs.readFileSync(path.join(root, "sidepanel.js"), "utf8");
  const policy = fs.readFileSync(path.join(root, "automation-policy.js"), "utf8");
  const attachment = fs.readFileSync(path.join(root, "pdf-attachment.js"), "utf8");
  assert.deepEqual(manifest.permissions.sort(), ["activeTab", "clipboardWrite", "scripting", "sidePanel"]);
  assert.deepEqual(manifest.optional_permissions, ["cookies"]);
  assert.deepEqual(manifest.optional_host_permissions.sort(), [
    "https://agente-de-candidaturas.onrender.com/*",
    "https://candidaturacerta.com.br/*",
  ]);
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.equal(manifest.background.service_worker, "background.js");
  assert.equal(manifest.minimum_chrome_version, "116");
  assert.doesNotMatch(filler, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
  assert.doesNotMatch(popup, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit/);
  assert.doesNotMatch(widget, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
  assert.doesNotMatch(sidepanel, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit/);
  assert.match(background, /https:\/\/candidaturacerta\.com\.br\$\{path\}/);
  assert.match(background, /chrome\.cookies\.get/);
  assert.doesNotMatch(background, /agente_refresh_token|X-CC-Refresh-Token/);
  assert.match(background, /requirePopupSender/);
  assert.match(background, /CC_GET_APPLICATION_PDFS/);
  assert.doesNotMatch(background, /storage\.local|storage\.sync/);
  assert.match(popup, /chrome\.permissions\.request\(sitePermission\(\)\)/);
  assert.match(popup, /executeScript\(\{ target: \{ tabId: activeTab\.id \}, files: \["field-filler\.js", "copilot-widget\.js"\] \}\)/);
  assert.match(popupHtml, /Confirmei que o portal permite preenchimento assistido/);
  assert.match(popupHtml, /transferir os PDFs selecionados para campos de currículo ou carta nesta página/);
  assert.match(popupHtml, /PDFs da sua biblioteca/);
  assert.match(popup, /CC_LIST_DOCUMENTS/);
  assert.match(popup, /CC_GET_APPLICATION_PDFS/);
  assert.ok(popup.includes("https:"));
  assert.ok(!popup.includes("https?:"));
  assert.match(popupHtml, /Você revisa e envia/i);
  assert.match(popupHtml, /automation-policy\.js/);
  assert.match(policy, /linkedin\.com/);
  assert.match(popupHtml, /id="attachmentConsent"/);
  assert.match(popup, /CandidaturaCertaPdfAttachment\.attachPdfsInPage/);
  assert.doesNotMatch(attachPdfsInPage.toString(), /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
  assert.doesNotMatch(attachment, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
});
