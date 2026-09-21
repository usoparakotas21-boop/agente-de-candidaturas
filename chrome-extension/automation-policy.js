(() => {
  const restrictedDomains = [
    { domain: "linkedin.com", brand: "LinkedIn", reason: "proíbe extensões de terceiros que automatizem atividade no site" },
    { domain: "linkedin.cn", brand: "LinkedIn", reason: "proíbe extensões de terceiros que automatizem atividade no site" },
    { domain: "jobbol.com.br", brand: "Jobbol", reason: "proíbe bots, scripts e extensões para acessar ou interagir com a plataforma sem autorização expressa" },
    { domain: "glassdoor.com", brand: "Glassdoor", reason: "proíbe software ou agentes automatizados sem autorização expressa" },
  ];
  const supportedDomains = ["gupy.io", "vagas.com.br", "infojobs.com.br"];

  function normalizedHost(hostname) {
    return typeof hostname === "string" ? hostname.trim().toLowerCase().replace(/\.$/, "") : "";
  }

  function matchesDomain(host, domain) {
    return host === domain || host.endsWith(`.${domain}`);
  }

  function isRestrictedAutomationHost(hostname) {
    const host = normalizedHost(hostname);
    return restrictedDomains.some(({ domain }) => matchesDomain(host, domain));
  }

  function isSupportedAutomationHost(hostname) {
    const host = normalizedHost(hostname);
    return !isRestrictedAutomationHost(host) && supportedDomains.some(domain => matchesDomain(host, domain));
  }

  function restrictedMessageFor(hostname) {
    const host = normalizedHost(hostname);
    const policy = restrictedDomains.find(({ domain }) => matchesDomain(host, domain));
    return policy
      ? `${policy.brand} ${policy.reason}. Nada foi acessado ou preenchido. Abra o portal de carreiras do empregador e use o complemento somente se aquele destino permitir.`
      : "";
  }

  const api = {
    isRestrictedAutomationHost,
    restrictedMessageFor,
    isSupportedAutomationHost,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaAutomationPolicy = api;
})();
