(() => {
  const MAX_DESCRIPTION_LENGTH = 12000;

  function visibleText(element) {
    if (!element || element.getAttribute?.("aria-hidden") === "true") return "";
    if (element.closest?.("form, [aria-hidden='true']")) return "";
    if (typeof element.getClientRects === "function" && element.getClientRects().length === 0) return "";
    const value = typeof element.innerText === "string" ? element.innerText : element.textContent;
    return String(value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }

  function firstText(root, selectors, limit) {
    for (const selector of selectors) {
      for (const element of root.querySelectorAll?.(selector) || []) {
        const value = visibleText(element);
        if (value) return value.slice(0, limit);
      }
    }
    return "";
  }

  function longestDescription(root) {
    const selectors = [
      "[data-testid*='job-description']",
      "[data-cy*='job-description']",
      "[id*='job-description']",
      "[class*='job-description']",
      "[class*='vacancy-description']",
      "[data-testid*='description']",
      "article",
    ];
    let best = "";
    for (const selector of selectors) {
      for (const element of root.querySelectorAll?.(selector) || []) {
        const value = visibleText(element);
        if (value.length > best.length) best = value.slice(0, MAX_DESCRIPTION_LENGTH);
      }
      if (best.length >= 500) break;
    }
    return best.length >= 80 ? best : "";
  }

  function extractVisibleJobContext(root = document) {
    const title = firstText(root, ["main h1", "article h1", "h1"], 200)
      || String(root.title || "").trim().slice(0, 200);
    const company = firstText(root, [
      "[data-testid*='company-name']", "[data-cy*='company-name']",
      "[class*='company-name']", "[itemprop='hiringOrganization']",
    ], 200);
    const location = firstText(root, [
      "[data-testid*='location']", "[data-cy*='location']",
      "[class*='job-location']", "[itemprop='jobLocation']",
    ], 200);
    return { title, company, location, description: longestDescription(root) };
  }

  const api = { extractVisibleJobContext };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaJobContext = api;
})();
