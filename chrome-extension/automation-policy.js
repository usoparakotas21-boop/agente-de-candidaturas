(() => {
  const restrictedDomains = [
    { domain: "linkedin.com", brand: "LinkedIn", reason: "proíbe extensões de terceiros que automatizem atividade no site" },
    { domain: "linkedin.cn", brand: "LinkedIn", reason: "proíbe extensões de terceiros que automatizem atividade no site" },
    { domain: "jobbol.com.br", brand: "Jobbol", reason: "proíbe bots, scripts e extensões para acessar ou interagir com a plataforma sem autorização expressa" },
    { domain: "glassdoor.com", brand: "Glassdoor", reason: "proíbe software ou agentes automatizados sem autorização expressa" },
  ];

  function isRestrictedAutomationHost(hostname) {
    if (typeof hostname !== "string") return false;
    const host = hostname.trim().toLowerCase().replace(/\.$/, "");
    return restrictedDomains.some(({ domain }) => host === domain || host.endsWith(`.${domain}`));
  }

  function restrictedMessageFor(hostname) {
    if (typeof hostname !== "string") return "";
    const host = hostname.trim().toLowerCase().replace(/\.$/, "");
    const policy = restrictedDomains.find(({ domain }) => host === domain || host.endsWith(`.${domain}`));
    return policy
      ? `${policy.brand} ${policy.reason}. Nada foi acessado ou preenchido. Abra o portal de carreiras do empregador e use o complemento somente se aquele destino permitir.`
      : "";
  }

  const api = {
    isRestrictedAutomationHost,
    restrictedMessageFor,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaAutomationPolicy = api;
})();
