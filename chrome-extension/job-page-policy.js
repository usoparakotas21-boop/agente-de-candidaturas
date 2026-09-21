(() => {
  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function isLikelyJobPage(url, visibleText = "") {
    let parsed;
    try { parsed = new URL(url); } catch { return false; }
    if (parsed.protocol !== "https:") return false;

    const path = normalize(parsed.pathname.replace(/%2f/gi, "/"));
    if (/(?:^|\/)(?:jobs?|vagas?|ofertas?|oportunidades?|positions?|carreiras?|candidatar|apply|application)(?:\/|$|-)/.test(path)) {
      return true;
    }

    const rawText = typeof visibleText === "function" ? visibleText() : visibleText;
    const text = normalize(String(rawText || "").slice(0, 16000)).replace(/[^a-z0-9]+/g, " ");
    return /\b(candidatar se|candidate se|enviar candidatura|enviar curriculo|apply for this job|apply now|submit application|inscreva se nesta vaga|quero me candidatar)\b/.test(text);
  }

  const api = { isLikelyJobPage };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaJobPagePolicy = api;
})();
