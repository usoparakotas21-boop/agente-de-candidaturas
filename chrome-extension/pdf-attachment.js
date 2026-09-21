(() => {
  function classifyFileField(descriptor) {
    const text = String([
      descriptor?.labels,
      descriptor?.ariaLabel,
      descriptor?.title,
      descriptor?.name,
      descriptor?.id,
      descriptor?.groupLabel,
    ].filter(Boolean).join(" ")).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ");
    if (/passport|passaporte|photo|foto|certificate|certificado|diploma|work permit|visto/.test(text)) return null;
    if (/cover\s*letter|letter\s*of\s*(application|motivation)|carta\s*(de\s*)?(apresentacao|candidatura|motivacao)/.test(text)) return "letter";
    if (/curriculum\s*vitae|resume|curriculo|\bcv\b/.test(text)) return "resume";
    return null;
  }

  // This function is injected into the active page after a second, separate consent.
  // Keep it self-contained because chrome.scripting serializes only this function.
  function attachPdfsInPage(selected) {
    const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ");
    const classify = descriptor => {
      const text = normalize([
        descriptor.labels, descriptor.ariaLabel, descriptor.title,
        descriptor.name, descriptor.id, descriptor.groupLabel,
      ].filter(Boolean).join(" "));
      if (/passport|passaporte|photo|foto|certificate|certificado|diploma|work permit|visto/.test(text)) return null;
      if (/cover\s*letter|letter\s*of\s*(application|motivation)|carta\s*(de\s*)?(apresentacao|candidatura|motivacao)/.test(text)) return "letter";
      if (/curriculum\s*vitae|resume|curriculo|\bcv\b/.test(text)) return "resume";
      return null;
    };
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    const descriptors = inputs.map(input => {
      const fieldset = input.closest("fieldset,[role=group]");
      const style = getComputedStyle(input);
      const visible = input.getClientRects().length > 0 && style.display !== "none" && style.visibility !== "hidden";
      const labels = input.labels ? [...input.labels].map(label => label.innerText || label.textContent || "").join(" ") : "";
      const hasVisibleLabel = input.labels ? [...input.labels].some(label => {
        const labelStyle = getComputedStyle(label);
        return label.getClientRects().length > 0 && labelStyle.display !== "none" && labelStyle.visibility !== "hidden";
      }) : false;
      const groupStyle = fieldset ? getComputedStyle(fieldset) : null;
      const hasVisibleGroup = Boolean(fieldset && fieldset.getClientRects().length > 0 && groupStyle.display !== "none" && groupStyle.visibility !== "hidden");
      const groupLabel = fieldset ? String(fieldset.innerText || fieldset.textContent || "").slice(0, 500) : "";
      const accept = String(input.accept || "").toLowerCase();
      const acceptsPdf = !accept || accept.includes(".pdf") || accept.includes("application/pdf") || accept.includes("*/*");
      return { input, kind: classify({ labels, ariaLabel: input.getAttribute("aria-label"), title: input.title, name: input.name, id: input.id, groupLabel }), eligible: (visible || hasVisibleLabel || hasVisibleGroup) && !input.disabled && acceptsPdf };
    });
    const plan = [];
    for (const kind of ["resume", "letter"]) {
      const file = selected?.[kind];
      if (!file) continue;
      const matches = descriptors.filter(item => item.eligible && item.kind === kind);
      if (matches.length !== 1) {
        return { ok: false, message: matches.length
          ? `Há mais de um campo de ${kind === "resume" ? "currículo" : "carta"} compatível. Anexe o documento manualmente para escolher o campo correto.`
          : `Não encontrei um campo de ${kind === "resume" ? "currículo" : "carta"} claramente identificado e compatível com PDF. Nada foi anexado.` };
      }
      if (matches[0].input.files?.length) {
        return { ok: false, message: `O campo de ${kind === "resume" ? "currículo" : "carta"} já contém um arquivo. Nada foi substituído.` };
      }
      plan.push({ input: matches[0].input, file });
    }
    if (!plan.length) return { ok: false, message: "Selecione ao menos um PDF antes de anexar." };
    try {
      const prepared = plan.map(({ input, file }) => {
        if (!file || !/^[A-Za-z0-9._-]{1,120}\.pdf$/i.test(file.name) || typeof file.base64 !== "string") {
          throw new Error("Um arquivo selecionado não parece ser um PDF válido.");
        }
        const binary = atob(file.base64);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        if (bytes.length < 5 || new TextDecoder().decode(bytes.subarray(0, 5)) !== "%PDF-") {
          throw new Error("PDF inválido.");
        }
        const item = new File([bytes], file.name, { type: "application/pdf" });
        const transfer = new DataTransfer();
        transfer.items.add(item);
        return { input, transfer };
      });
      prepared.forEach(({ input, transfer }) => {
        input.files = transfer.files;
        input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      const labels = plan.map(item => item.file.name);
      return { ok: true, message: `PDF(s) anexado(s): ${labels.join(" e ")}. Confira os nomes e continue a revisão no portal; nada foi enviado.` };
    } catch {
      return { ok: false, message: "O navegador não permitiu anexar estes PDFs. Nenhum formulário foi enviado." };
    }
  }

  const api = { classifyFileField, attachPdfsInPage };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalThis.CandidaturaCertaPdfAttachment = api;
})();
