(() => {
  const api = (() => {
    const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    const unsafe = /captcha|recaptcha|hcaptcha|password|senha|confirm|verification|verificacao|security|seguranca|token|consent|terms|privacy|accept|agreement|termos|politica|motivation|motivacao|cover letter|carta de apresentacao|why (do|are)|porque (quer|deseja)|salary|pretensao|remuneracao|company|empresa|resume upload|curriculo|curriculum|portfolio|file|anexo|birth|nascimento|nationality|nacionalidade|eligib|authorization|autorizacao|work permit|visto|deficiencia|disability|race|etnia|gender|genero/;
    const allowedTypes = new Set(["text", "email", "tel", "url", "textarea", "select-one"]);
    const stateNames = {
      AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal",
      ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul",
      MG: "Minas Gerais", PA: "Pará", PB: "Paraíba", PR: "Paraná", PE: "Pernambuco", PI: "Piauí",
      RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RS: "Rio Grande do Sul", RO: "Rondônia", RR: "Roraima",
      SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins"
    };

    function classify(descriptor) {
      if (!descriptor || descriptor.disabled || descriptor.readOnly || descriptor.visible === false) return null;
      const tag = String(descriptor.tagName || "").toLowerCase();
      const type = tag === "textarea" ? "textarea" : tag === "select" ? "select-one" : String(descriptor.type || "text").toLowerCase();
      if (!allowedTypes.has(type) || !["input", "textarea", "select"].includes(tag) || (tag === "select" && descriptor.multiple)) return null;
      const autocomplete = normalize(descriptor.autocomplete);
      const signals = normalize([descriptor.label, descriptor.ariaLabel, descriptor.placeholder, descriptor.name, descriptor.id].filter(Boolean).join(" "));
      if ((!signals && !autocomplete) || unsafe.test(signals)) return null;

      if (autocomplete === "given name" || /\b(first name|given name|prenom)\b/.test(signals)) return "first_name";
      if (autocomplete === "family name" || /\b(last name|family name|surname|sobrenome)\b/.test(signals)) return "last_name";
      if (autocomplete === "email" || /\b(e mail|email address|email|correo)\b/.test(signals)) return "email";
      if (autocomplete === "tel" || /\b(phone|telephone|mobile|cellphone|celular|telefone|whatsapp)\b/.test(signals)) return "phone";
      if (/\b(linkedin)\b/.test(signals)) return "linkedin";
      if (/\b(personal website|website|portfolio site|site pessoal|website pessoal)\b/.test(signals)) return "website";
      if (autocomplete === "address level2" || /\b(city|cidade|municipio|localidade)\b/.test(signals)) return "city";
      if (autocomplete === "address level1" || /\b(state|province|estado|provincia)\b/.test(signals)) return "state";
      if (/\b(location|localizacao)\b/.test(signals)) return "location";
      if (/\b(full name|nome completo|candidate name|applicant name)\b/.test(signals)) return "name";
      if (/\b(professional headline|professional title|current position|cargo atual|titulo profissional)\b/.test(signals)) return "headline";
      if (/\b(professional summary|about me|about you|short bio|biography|resumo profissional|sobre voce|apresentacao profissional)\b/.test(signals)) return "summary";
      if (/\b(work experience|professional experience|experiencia profissional|historico profissional)\b/.test(signals)) return "experiences";
      if (/\b(skills|competencies|competencias|habilidades)\b/.test(signals)) return "skills";
      if (/\b(education|academic background|formacao academica|escolaridade)\b/.test(signals)) return "education";
      if (/\b(languages|idiomas|linguas)\b/.test(signals)) return "languages";
      if (autocomplete === "name" || /^name$/.test(normalize(descriptor.name)) || /^nome$/.test(normalize(descriptor.label))) return "name";
      return null;
    }

    function valueFor(key, profile) {
      const nameParts = String(profile.name || "").trim().split(/\s+/).filter(Boolean);
      const values = {
        name: profile.name,
        first_name: nameParts[0] || "",
        last_name: nameParts.length > 1 ? nameParts.slice(1).join(" ") : "",
        email: profile.email,
        phone: profile.phone,
        linkedin: profile.linkedin,
        website: profile.website,
        location: profile.location,
        city: String(profile.location || "").split(/[,/|–—-]/).map(part => part.trim()).filter(Boolean)[0] || "",
        state: String(profile.location || "").split(/[,/|–—-]/).map(part => part.trim()).filter(Boolean)[1] || "",
        headline: profile.headline,
        summary: profile.summary,
        experiences: (profile.experiences || []).map(item => [item.role, item.company, item.period, item.description].filter(Boolean).join(" — ")).join("\n"),
        education: (profile.education || []).map(item => [item.course, item.institution, item.period].filter(Boolean).join(" — ")).join("\n"),
        skills: (profile.skills || []).join(", "),
        languages: (profile.languages || []).join(", ")
      };
      return typeof values[key] === "string" ? values[key].trim() : "";
    }

    function createFillPlan(descriptors, profile) {
      const plan = [];
      for (let index = 0; index < descriptors.length; index += 1) {
        const descriptor = descriptors[index];
        const key = classify(descriptor);
        let value = key ? valueFor(key, profile || {}) : "";
        if (!key || !value || descriptor.hasValue || (descriptor.maxLength > 0 && value.length > descriptor.maxLength)) continue;
        if (String(descriptor.tagName || "").toLowerCase() === "select") {
          const candidates = [normalize(value)];
          if (key === "state") {
            const stateCode = Object.keys(stateNames).find(code => code === value.toUpperCase())
              || Object.entries(stateNames).find(([, name]) => normalize(name) === normalize(value))?.[0];
            if (stateCode) candidates.push(normalize(stateNames[stateCode]), normalize(stateCode));
          }
          const option = (descriptor.options || []).find(item =>
            !item.disabled && item.value && candidates.some(candidate => candidate === normalize(item.value) || candidate === normalize(item.text))
          );
          if (!option) continue;
          value = option.value;
        }
        plan.push({ index, key, value });
      }
      return plan;
    }
    return { createFillPlan, valueFor, normalize };
  })();

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaFieldFiller = api;
  if (typeof chrome === "undefined" || !chrome.runtime?.onMessage || globalThis.__ccAutofillListenerInstalled) return;
  globalThis.__ccAutofillListenerInstalled = true;

  function describe(element) {
    const tagName = element.tagName.toLowerCase();
    const style = getComputedStyle(element);
    const visible = element.getClientRects().length > 0 && style.display !== "none" && style.visibility !== "hidden" && element.getAttribute("aria-hidden") !== "true";
    const labels = element.labels ? [...element.labels].map(label => label.innerText || label.textContent || "").join(" ") : "";
    return {
      tagName, type: tagName === "textarea" ? "textarea" : element.type,
      autocomplete: element.getAttribute("autocomplete") || "", label: labels,
      ariaLabel: element.getAttribute("aria-label") || "", placeholder: element.getAttribute("placeholder") || "",
      name: element.getAttribute("name") || "", id: element.id || "",
      disabled: element.disabled, readOnly: element.readOnly, multiple: Boolean(element.multiple), visible, maxLength: element.maxLength,
      options: tagName === "select" ? [...element.options].map(option => ({ value: option.value, text: option.label || option.textContent || "", disabled: option.disabled })) : [],
      hasValue: String(element.value || "").trim().length > 0 && !(tagName === "select" && element.selectedOptions?.[0]?.dataset?.placeholder === "true")
    };
  }

  function fillProfileFields(profile) {
    try {
      const elements = [...document.querySelectorAll("input, textarea, select")];
      let filled = 0;
      const filledKeys = new Set();

      function putValue(element, key, value) {
        if (!element || !value || !["INPUT", "TEXTAREA"].includes(element.tagName)) return false;
        const type = element.tagName === "TEXTAREA" ? "textarea" : String(element.type || "text").toLowerCase();
        if (!["text", "email", "tel", "url", "textarea"].includes(type)) return false;
        const descriptor = describe(element);
        const signal = api.normalize([descriptor.label, descriptor.ariaLabel, descriptor.placeholder, descriptor.name, descriptor.id].join(" "));
        if (descriptor.disabled || descriptor.readOnly || !descriptor.visible || descriptor.hasValue || /captcha|senha|password|consent|termos|privacy|salary|pretensao|curriculo|resume|cover|carta|file|birth|nascimento|gender|genero|race|etnia|deficiencia|disability/.test(signal)) return false;
        if (descriptor.maxLength > 0 && value.length > descriptor.maxLength) return false;
        const prototype = element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
        if (!setter) return false;
        setter.call(element, value);
        element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
        filled += 1;
        filledKeys.add(key);
        return true;
      }

      const portal = globalThis.CandidaturaCertaPortalSelectors?.getPortalDefinition?.(location.hostname);
      const usedElements = new Set();
      if (portal) {
        for (const [key, selectors] of Object.entries(portal.fields || {})) {
          const value = api.valueFor(key, profile || {});
          if (!value) continue;
          const element = (selectors || []).map(selector => document.querySelector(selector)).find(Boolean);
          if (element && putValue(element, key, value)) usedElements.add(element);
        }
      }

      const descriptors = elements.map(describe);
      const plan = api.createFillPlan(descriptors, profile || {});
      for (const item of plan) {
        const element = elements[item.index];
        if (usedElements.has(element)) continue;
        if (element.tagName === "SELECT") {
          const optionExists = [...element.options].some(option => !option.disabled && option.value === item.value);
          if (!optionExists) continue;
          element.value = item.value;
          element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
          filled += 1;
          filledKeys.add(item.key);
          continue;
        }
        putValue(element, item.key, item.value);
      }
      return { ok: true, filled, filledKeys: [...filledKeys], note: portal?.note || "" };
    } catch {
      return { ok: false, message: "Não foi possível preencher esta página. Confira se o formulário ainda está aberto." };
    }
  }

  api.fillProfileFields = fillProfileFields;
  const messageListener = (message, _sender, sendResponse) => {
    if (message?.type !== "CC_FILL_PROFILE_FIELDS") return;
    sendResponse(fillProfileFields(message.profile || {}));
    return false;
  };
  chrome.runtime.onMessage.addListener(messageListener);
  globalThis.__ccAutofillMessageListener = messageListener;
})();
