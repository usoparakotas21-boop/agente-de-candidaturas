const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createFillPlan } = require("../chrome-extension/field-filler.js");
const { isRestrictedAutomationHost } = require("../chrome-extension/automation-policy.js");
const { isLikelyJobPage } = require("../chrome-extension/job-page-policy.js");
const { extractVisibleJobContext } = require("../chrome-extension/job-context.js");
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

test("extrai texto visível de contexto profissional dentro do limite", () => {
  const visible = text => ({
    innerText: text,
    textContent: text,
    getAttribute: () => null,
    closest: () => null,
    getClientRects: () => [1],
  });
  const selectors = {
    "main h1": [visible("Analista de RH")],
    "[data-testid*='company-name']": [visible("Empresa Exemplo")],
    "[data-testid*='location']": [visible("Salvador, BA")],
    "[data-testid*='job-description']": [visible("Requisitos da vaga: recrutamento e seleção, Excel. " + "Descrição detalhada. ".repeat(1000))],
  };
  const result = extractVisibleJobContext({
    title: "Vaga — Gupy",
    querySelectorAll: selector => selectors[selector] || [],
  });
  assert.equal(result.title, "Analista de RH");
  assert.equal(result.company, "Empresa Exemplo");
  assert.equal(result.location, "Salvador, BA");
  assert.match(result.description, /Requisitos da vaga/);
  assert.equal(result.description.length, 12000);
});

test("ignora descrição escondida e texto dentro de formulários", () => {
  const hidden = { innerText: "vaga escondida", textContent: "vaga escondida", getAttribute: () => "true", getClientRects: () => [1] };
  const formOnly = { innerText: "informação digitada pela pessoa", textContent: "informação digitada pela pessoa", getAttribute: () => null, getClientRects: () => [1], closest: () => ({}) };
  const selectors = {
    "main h1": [], "article h1": [], h1: [],
    "[data-testid*='company-name']": [], "[data-cy*='company-name']": [], "[class*='company-name']": [], "[itemprop='hiringOrganization']": [],
    "[data-testid*='location']": [], "[data-cy*='location']": [], "[class*='job-location']": [], "[itemprop='jobLocation']": [],
    "[data-testid*='job-description']": [hidden], "[data-cy*='job-description']": [], "[id*='job-description']": [],
    "[class*='job-description']": [formOnly], "[class*='vacancy-description']": [], "[data-testid*='description']": [], article: [],
  };
  const result = extractVisibleJobContext({ title: "Vaga", querySelectorAll: selector => selectors[selector] || [] });
  assert.equal(result.description, "");
});

test("reconhece páginas de vagas e ações de candidatura sem ativar em páginas genéricas", () => {
  assert.equal(isLikelyJobPage("https://careers.gupy.io/jobs/123", "Detalhes da vaga"), true);
  assert.equal(isLikelyJobPage("https://careers.gupy.io/jobs/123", () => { throw new Error("não deve ler o texto"); }), true);
  assert.equal(isLikelyJobPage("https://www.vagas.com.br/vagas/v123", "Oportunidade"), true);
  assert.equal(isLikelyJobPage("https://empregos.infojobs.com.br/oferta/123", "Detalhes"), true);
  assert.equal(isLikelyJobPage("https://careers.example.org/job/123", "Página"), true);
  assert.equal(isLikelyJobPage("https://careers.example.org/about", "Clique em candidatar-se para esta vaga"), true);
  assert.equal(isLikelyJobPage("https://careers.example.org/login", "Entrar na sua conta"), false);
  assert.equal(isLikelyJobPage("http://careers.example.org/jobs/123", "Candidatar-se"), false);
  assert.equal(isLikelyJobPage("not a URL", "Candidatar-se"), false);
});

test("ativa e revoga o botão automático com permissão só para o domínio da vaga", async () => {
  const root = path.resolve(__dirname, "../chrome-extension");
  const registered = new Map();
  const injected = [];
  const listeners = [];
  const chrome = {
    runtime: {
      onMessage: { addListener: listener => listeners.push(listener) },
      getURL: file => `chrome-extension://test/${file}`,
    },
    permissions: { contains: async ({ origins = [] }) => origins.every(origin => origin === "https://careers.gupy.io/*") },
    tabs: { query: async () => [{ id: 17, url: "https://careers.gupy.io/jobs/123" }] },
    scripting: {
      getRegisteredContentScripts: async ({ ids }) => ids.flatMap(id => registered.has(id) ? [registered.get(id)] : []),
      registerContentScripts: async scripts => scripts.forEach(script => registered.set(script.id, script)),
      unregisterContentScripts: async ({ ids }) => ids.forEach(id => registered.delete(id)),
      executeScript: async script => { injected.push(script); return []; },
    },
    sidePanel: { setOptions: async () => {} },
  };
  const context = vm.createContext({ chrome, URL, console });
  context.importScripts = (...files) => files.forEach(file => vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context));
  vm.runInContext(fs.readFileSync(path.join(root, "background.js"), "utf8"), context);

  const request = (type) => new Promise((resolve, reject) => {
    const handled = listeners[0]({ type, tabId: 17 }, { url: "chrome-extension://test/popup.html" }, resolve);
    if (!handled) reject(new Error("worker did not accept the request"));
  });

  const enabled = await request("CC_ENABLE_AUTO_WIDGET");
  assert.deepEqual({ ok: enabled.ok, host: enabled.value.host, enabled: enabled.value.enabled }, { ok: true, host: "careers.gupy.io", enabled: true });
  const script = [...registered.values()][0];
  assert.equal(Array.from(script.matches).join(","), "https://careers.gupy.io/*");
  assert.equal(Array.from(script.js).join(","), "job-page-policy.js,job-context.js,field-filler.js,copilot-widget.js");
  assert.equal(script.persistAcrossSessions, true);
  assert.ok(injected.some(item => item.files?.includes("copilot-widget.js")));

  const disabled = await request("CC_DISABLE_AUTO_WIDGET");
  assert.deepEqual({ ok: disabled.ok, enabled: disabled.value.enabled }, { ok: true, enabled: false });
  assert.equal(registered.size, 0);
  assert.ok(injected.some(item => typeof item.func === "function"));
});

test("painel lateral exige consentimento e envia análise apenas da aba ATS ativa", async () => {
  const root = path.resolve(__dirname, "../chrome-extension");
  const listeners = [];
  const requests = [];
  const chrome = {
    runtime: {
      onMessage: { addListener: listener => listeners.push(listener) },
      getURL: file => `chrome-extension://test/${file}`,
    },
    permissions: { contains: async () => true },
    cookies: { get: async () => ({ value: "access-token" }) },
    tabs: {
      query: async () => [{ id: 17, url: "https://careers.gupy.io/jobs/123" }],
      get: async id => ({ id, url: "https://careers.gupy.io/jobs/123" }),
    },
    sidePanel: { setOptions: async () => {} },
  };
  const context = vm.createContext({ chrome, URL, console, fetch: async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ vacancy_analysis: { score: 80 } }) };
  } });
  context.importScripts = (...files) => files.forEach(file => vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context));
  vm.runInContext(fs.readFileSync(path.join(root, "background.js"), "utf8"), context);
  const jobDescription = "A vaga exige recrutamento e seleção. ".repeat(8);
  const response = await new Promise((resolve, reject) => {
    const handled = listeners[0]({
      type: "CC_ANALYZE_JOB", tabId: 17, requestId: "request-id",
      consent: true,
      useGemini: true,
      jobContext: { title: "Analista de RH", description: jobDescription },
    }, { url: "chrome-extension://test/sidepanel.html" }, resolve);
    if (!handled) reject(new Error("worker did not accept the request"));
  });
  assert.equal(response.ok, true);
  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /\/api\/copilot\/prepare$/);
  const body = JSON.parse(requests[0].options.body);
  assert.equal(body.analysis_only, true);
  assert.equal(body.consent_data_processing, true);
  assert.equal(body.consent_gemini_processing, true);
  assert.equal(body.portal_allowed, false);
  assert.equal(body.portal_host, "careers.gupy.io");
  assert.equal(body.job_title, "Analista de RH");
  assert.equal(body.job_description, jobDescription);
});

test("painel lateral explica análise, consentimentos e controle em linguagem simples", () => {
  const html = fs.readFileSync(path.join(__dirname, "../chrome-extension/sidepanel.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "../chrome-extension/sidepanel.js"), "utf8");
  assert.match(html, /Compare esta vaga com seu perfil/);
  assert.match(html, /nada será preenchido no portal nem enviado à empresa/);
  assert.match(html, /O Gemini fica desligado por padrão/);
  assert.match(html, /nome, e-mail e telefone ficam de fora/);
  assert.match(html, /Ver compatibilidade/);
  assert.match(script, /Aderência estimada:/);
  assert.match(script, /Preparações usadas neste mês/);
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
  const pagePolicy = fs.readFileSync(path.join(root, "job-page-policy.js"), "utf8");
  const sidepanel = fs.readFileSync(path.join(root, "sidepanel.js"), "utf8");
  const sidepanelHtml = fs.readFileSync(path.join(root, "sidepanel.html"), "utf8");
  const policy = fs.readFileSync(path.join(root, "automation-policy.js"), "utf8");
  const attachment = fs.readFileSync(path.join(root, "pdf-attachment.js"), "utf8");
  assert.deepEqual(manifest.permissions.sort(), ["activeTab", "clipboardWrite", "scripting", "sidePanel"]);
  assert.deepEqual(manifest.optional_permissions, ["cookies"]);
  assert.deepEqual(manifest.optional_host_permissions.sort(), [
    "https://*.gupy.io/*",
    "https://*.infojobs.com.br/*",
    "https://*.vagas.com.br/*",
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
  assert.match(sidepanel, /CC_ANALYZE_JOB/);
  assert.match(sidepanel, /extractVisibleJobContext/);
  assert.match(sidepanelHtml, /id="analysisConsent"/);
  assert.match(sidepanelHtml, /id="geminiConsent"/);
  assert.doesNotMatch(sidepanelHtml, /id="geminiConsent"[^>]*checked/);
  assert.match(sidepanelHtml, /id="analyzeJob"/);
  assert.match(background, /https:\/\/candidaturacerta\.com\.br\$\{path\}/);
  assert.match(background, /chrome\.cookies\.get/);
  assert.doesNotMatch(background, /agente_refresh_token|X-CC-Refresh-Token/);
  assert.match(background, /requirePopupSender/);
  assert.match(background, /registerContentScripts/);
  assert.match(background, /persistAcrossSessions: true/);
  assert.match(background, /CC_ENABLE_AUTO_WIDGET/);
  assert.match(background, /CC_DISABLE_AUTO_WIDGET/);
  assert.match(background, /CC_GET_APPLICATION_PDFS/);
  assert.doesNotMatch(background, /storage\.local|storage\.sync/);
  assert.match(popup, /chrome\.permissions\.request\(sitePermission\(\)\)/);
  assert.equal(manifest.version, "1.0.0");
  assert.equal(manifest.name, "Candidatura Certa — Copiloto");
  assert.equal(manifest.homepage_url, "https://candidaturacerta.com.br/");
  assert.deepEqual(manifest.icons, {
    "16": "icons/icon16.png",
    "32": "icons/icon32.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png",
  });
  for (const size of [16, 32, 48, 128]) {
    const iconPath = path.join(root, "icons", `icon${size}.png`);
    assert.equal(fs.existsSync(iconPath), true);
    const icon = fs.readFileSync(iconPath);
    assert.equal(icon.readUInt32BE(16), size);
    assert.equal(icon.readUInt32BE(20), size);
  }
  assert.match(popup, /executeScript\(\{ target: \{ tabId: activeTab\.id \}, files: \["job-page-policy\.js", "job-context\.js", "field-filler\.js", "copilot-widget\.js"\] \}\)/);
  assert.match(popup, /Ativar botão automaticamente neste domínio/);
  assert.match(popup, /chrome\.permissions\.request\(\{ origins: \[.*page\.origin/s);
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
  assert.match(widget, /isLikelyJobPage/);
  assert.match(widget, /extractVisibleJobContext/);
  assert.match(widget, /Compatibilidade estimada/);
  assert.match(widget, /Copiar resumo sugerido/);
  assert.match(background, /job_description: typeof jobContext\.description === "string"/);
  assert.match(pagePolicy, /apply now/);
  assert.match(pagePolicy, /candidatar se/);
  assert.doesNotMatch(pagePolicy, /fetch\s*\(|XMLHttpRequest/);
  assert.match(popupHtml, /id="attachmentConsent"/);
  assert.match(popup, /CandidaturaCertaPdfAttachment\.attachPdfsInPage/);
  assert.doesNotMatch(attachPdfsInPage.toString(), /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
  assert.doesNotMatch(attachment, /fetch\s*\(|XMLHttpRequest|\.submit\s*\(|requestSubmit|\.click\s*\(/);
});
