(() => {
  "use strict";
  if (document.querySelector(".cc-support-launcher")) return;

  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/static/support-chat.css?v=5";
  const styleGuard = document.createElement("style");
  styleGuard.textContent = ".cc-support-launcher,.cc-support-panel{visibility:hidden!important}";
  document.head.append(styleGuard);
  stylesheet.addEventListener("load", () => styleGuard.remove(), { once: true });
  stylesheet.addEventListener("error", () => {
    styleGuard.textContent = ".cc-support-launcher{position:fixed;z-index:10000;right:22px;bottom:22px;width:58px;height:58px;display:grid;place-items:center;padding:8px;border:0;border-radius:50%;background:#125ea0}.cc-support-avatar{width:40px;height:40px;display:grid;place-items:center;border-radius:50%;overflow:hidden}.cc-support-avatar img{width:100%;height:100%;object-fit:contain}";
  }, { once: true });
  document.head.append(stylesheet);

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const avatar = () => {
    const wrap = make("span", "cc-support-avatar");
    const image = document.createElement("img");
    image.src = "/static/favicon.svg?v=2";
    image.alt = "";
    image.setAttribute("aria-hidden", "true");
    wrap.append(image);
    return wrap;
  };

  const launcher = make("button", "cc-support-launcher");
  launcher.type = "button";
  launcher.title = "Fale com a Candidatura Certa";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "cc-support-panel");
  launcher.setAttribute("aria-label", "Abrir chat de suporte da Candidatura Certa");
  launcher.prepend(avatar());

  const panel = make("section", "cc-support-panel");
  panel.id = "cc-support-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "false");
  panel.setAttribute("aria-labelledby", "cc-support-heading");

  const header = make("header", "cc-support-head");
  header.append(avatar());
  const title = make("div", "cc-support-title");
  const heading = make("strong", "", "Candidatura Certa");
  heading.id = "cc-support-heading";
  title.append(heading, make("span", "", "Assistente virtual · Suporte geral"));
  const close = make("button", "cc-support-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "Fechar chat");
  header.append(title, close);

  const messages = make("div", "cc-support-messages");
  messages.setAttribute("aria-live", "polite");
  messages.setAttribute("aria-relevant", "additions text");
  const disclosure = make("p", "cc-support-disclosure", "Não envie senhas, tokens ou dados sensíveis. Sua dúvida é enviada à API Gemini para classificar o tema; a Candidatura Certa não salva o texto do chat.");
  const footer = make("div", "cc-support-footer");
  const form = make("form", "cc-support-form");
  const input = make("textarea", "cc-support-input");
  input.rows = 1;
  input.maxLength = 1200;
  input.required = true;
  input.setAttribute("aria-label", "Escreva sua dúvida");
  input.placeholder = "Escreva sua dúvida…";
  const send = make("button", "cc-support-send", "Enviar");
  send.type = "submit";
  form.append(input, send);
  const suggestions = make("div", "cc-support-suggestions");
  suggestions.setAttribute("role", "group");
  suggestions.setAttribute("aria-label", "Perguntas comuns");
  [
    "Como funciona o site?",
    "Como conecto Gmail ou Outlook?",
    "Quais são os planos e limites?",
    "Como gero meu currículo e minha carta?",
    "Aceita Pix para pagar?",
    "Onde baixo meus documentos?",
    "Como cancelo minha assinatura?",
  ].forEach((question) => {
    const suggestion = make("button", "cc-support-suggestion", question);
    suggestion.type = "button";
    suggestion.addEventListener("click", () => {
      if (send.disabled) return;
      input.value = question;
      form.requestSubmit();
    });
    suggestions.append(suggestion);
  });
  const links = make("div", "cc-support-links");
  const help = document.createElement("a");
  help.href = "mailto:contato@candidaturacerta.com.br";
  help.textContent = "E-mail do suporte";
  const faq = document.createElement("a");
  faq.href = "/ajuda";
  faq.textContent = "Central de ajuda";
  const whatsapp = document.createElement("a");
  whatsapp.href = "https://wa.me/5571991824951";
  whatsapp.target = "_blank";
  whatsapp.rel = "noopener noreferrer";
  whatsapp.textContent = "WhatsApp (71) 99182-4951";
  links.append(help, faq, whatsapp);
  const status = make("p", "cc-support-status");
  status.setAttribute("role", "status");
  footer.append(disclosure, form, links, status);
  panel.append(header, messages, footer);
  document.body.append(launcher, panel);

  // Move the fixed launcher above the page footer while it is on screen so it
  // cannot cover the support links on narrow viewports.
  const pageFooter = document.querySelector(".cc-support-safe-footer, .global-footer");
  if (pageFooter && "IntersectionObserver" in window) {
    const setFooterMode = (nearFooter) => {
      launcher.classList.toggle("cc-support-near-footer", nearFooter);
      panel.classList.toggle("cc-support-near-footer", nearFooter);
    };
    const footerObserver = new IntersectionObserver(([entry]) => {
      setFooterMode(Boolean(entry && entry.isIntersecting));
    }, { threshold: 0 });
    footerObserver.observe(pageFooter);
  }

  const addMessage = (role, text, pending = false) => {
    const bubble = make("div", "cc-support-message", text);
    bubble.dataset.role = role;
    if (pending) bubble.dataset.pending = "true";
    messages.append(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  };
  addMessage("assistant", "Olá! Posso explicar os planos, limites, vagas, documentos, pagamentos e privacidade. Como posso ajudar?");
  messages.append(suggestions);

  const open = () => {
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    input.focus();
  };
  const shut = () => {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  };
  launcher.addEventListener("click", () => (panel.hidden ? open() : shut()));
  close.addEventListener("click", shut);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) shut();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    status.textContent = "";
    suggestions.hidden = true;
    addMessage("user", message);
    input.value = "";
    input.disabled = true;
    send.disabled = true;
    send.textContent = "…";
    const pending = addMessage("assistant", "Consultando a base de ajuda…", true);
    try {
      const response = await fetch("/api/support-chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Não foi possível responder agora.");
      pending.textContent = payload.answer || "Não encontrei essa informação na base de ajuda.";
      delete pending.dataset.pending;
    } catch (error) {
      pending.remove();
      status.textContent = error.message || "O chat está temporariamente indisponível. Use os canais de suporte abaixo.";
    } finally {
      input.disabled = false;
      send.disabled = false;
      send.textContent = "Enviar";
      input.focus();
    }
  });
})();
