(() => {
  // These selectors are deliberately limited to ordinary professional fields.
  // They never target consent, salary, uploads, CAPTCHA, or submit controls.
  const portals = [
    {
      id: "gupy",
      domains: ["gupy.io"],
      fields: {
        first_name: ["input[name='firstName']", "input[data-testid*='first-name']"],
        last_name: ["input[name='lastName']", "input[data-testid*='last-name']"],
        email: ["input[type='email']", "input[name*='email']"],
        phone: ["input[type='tel']", "input[name*='phone']", "input[name*='telefone']"],
        headline: ["input[name*='headline']", "input[data-testid*='headline']"],
        summary: ["textarea[name*='summary']", "textarea[data-testid*='summary']"],
        linkedin: ["input[name*='linkedin']", "input[data-testid*='linkedin']"]
      },
      submit_buttons: ["button[data-testid='submit-button']", "button[data-testid='next-step-button']", "button[type='submit']", "button:contains('Avançar')", "button:contains('Próximo')", "button:contains('Enviar')"]
    },
    {
      id: "vagas",
      domains: ["vagas.com.br"],
      fields: {
        name: ["input#Nome", "input[name='nome']", "input[name='name']"],
        email: ["input#Email", "input[name='email']", "input[type='email']"],
        phone: ["input#Celular", "input[name='celular']", "input[name='telefone']"],
        headline: ["input#ObjetivoProfissional", "input[name='objetivo']"],
        summary: ["textarea#ResumoProfissional", "textarea[name='resumo']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["input[type='submit']", "button#btn-candidatar", "button:contains('Candidatar-se')", "button[type='submit']"]
    },
    {
      id: "infojobs",
      domains: ["infojobs.com.br"],
      fields: {
        name: ["input[name='name']", "input[name='nome']", "input[autocomplete='name']"],
        email: ["input[type='email']", "input[name*='email']"],
        phone: ["input[type='tel']", "input[name*='phone']", "input[name*='telefone']"],
        headline: ["input[name*='title']", "input[name*='cargo']"],
        summary: ["textarea[name*='summary']", "textarea[name*='resumo']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button.btn-primary", "button[type='submit']", "button:contains('Candidatar')"]
    },
    {
      id: "catho",
      domains: ["catho.com.br"],
      fields: {
        name: ["input[name='nome']", "input[name='name']", "input[autocomplete='name']"],
        email: ["input[name='email']", "input[type='email']"],
        phone: ["input[name='celular']", "input[name='telefone']", "input[type='tel']"],
        headline: ["input[name='cargo']", "input[name='objetivo']"],
        summary: ["textarea[name='resumo']", "textarea[name='summary']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button[type='submit']", "button:contains('Enviar currículo')"]
    },
    {
      id: "empregos",
      domains: ["empregos.com.br"],
      fields: {
        name: ["input[name='nome']", "input[name='name']", "input[autocomplete='name']"],
        email: ["input[name='email']", "input[type='email']"],
        phone: ["input[name='telefone']", "input[name='celular']", "input[type='tel']"],
        headline: ["input[name='cargo']", "input[name='titulo']"],
        summary: ["textarea[name='resumo']", "textarea[name='sobre']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button[type='submit']", "button:contains('Candidatar')"]
    },
    {
      id: "solides",
      domains: ["solides.com.br"],
      fields: {
        name: ["input[name='name']", "input[name='nome']", "input[autocomplete='name']"],
        email: ["input[type='email']", "input[name*='email']"],
        phone: ["input[type='tel']", "input[name*='phone']", "input[name*='telefone']"],
        headline: ["input[data-testid*='title']", "input[name*='cargo']"],
        summary: ["textarea[data-testid*='about-me']", "textarea[name*='summary']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button[type='submit']", "button:contains('Finalizar')"],
      note: "Listas suspensas personalizadas e perguntas não padronizadas ficam para revisão manual."
    },
    {
      id: "linkedin",
      domains: ["linkedin.com"],
      fields: {
        name: ["input[name*='name']", "input[id*='name']"],
        email: ["input[type='email']", "input[name*='email']"],
        phone: ["input[type='tel']", "input[name*='phoneNumber']", "input[name*='phone']"],
        headline: ["input[name*='headline']"],
        summary: ["textarea[name*='summary']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button[type='submit']", "button[aria-label*='Submit']", "button[aria-label*='Submit application']"]
    },
    {
      id: "indeed",
      domains: ["indeed.com", "indeed.com.br"],
      fields: {
        name: ["input[name*='name']", "input[id*='applicant-name']"],
        email: ["input[type='email']", "input[name*='email']"],
        phone: ["input[type='tel']", "input[name*='phone']"],
        headline: ["input[name*='headline']", "input[name*='title']"],
        summary: ["textarea[name*='summary']", "textarea[name*='letter']"],
        linkedin: ["input[name*='linkedin']"]
      },
      submit_buttons: ["button[type='submit']", "button:contains('Continue')", "button:contains('Submit')"]
    }
  ];

  function normalizeHost(hostname) {
    return typeof hostname === "string" ? hostname.trim().toLowerCase().replace(/\.$/, "") : "";
  }

  function matchesDomain(host, domain) {
    return host === domain || host.endsWith(`.${domain}`);
  }

  function getPortalDefinition(hostname) {
    const host = normalizeHost(hostname);
    return portals.find(portal => portal.domains.some(domain => matchesDomain(host, domain))) || null;
  }

  const api = { getPortalDefinition, normalizeHost };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaPortalSelectors = api;
})();
