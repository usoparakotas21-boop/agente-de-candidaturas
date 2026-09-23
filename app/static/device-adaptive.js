(() => {
  const isMobile = () => {
    const userAgentMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const screenMobile = window.innerWidth <= 768;
    return userAgentMobile || screenMobile;
  };

  function applyDeviceAdaptation() {
    const mobile = isMobile();
    document.body.classList.toggle("is-mobile-device", mobile);
    document.body.classList.toggle("is-desktop-device", !mobile);

    // Na visualização mobile, ocultar links de download de extensão desktop
    if (mobile) {
      document.querySelectorAll(".desktop-extension-only, [data-extension-only]").forEach(el => {
        el.style.display = "none";
      });
      document.querySelectorAll(".mobile-only, [data-mobile-only]").forEach(el => {
        el.style.display = "";
      });
    }

    // Registrar Service Worker do PWA se suportado
    if ("serviceWorker" in navigator && !window.__ccSwRegistered) {
      window.__ccSwRegistered = true;
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }

  // PWA Deferred Prompt Handling
  let deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const pwaBtn = document.getElementById("pwaInstallBtn");
    if (pwaBtn) {
      pwaBtn.style.display = "inline-flex";
      pwaBtn.onclick = async () => {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === "accepted") {
          pwaBtn.style.display = "none";
        }
        deferredPrompt = null;
      };
    }
  });

  // Utilitário de Cópia Rápida 1-Toque no celular
  async function copyToClipboard(text, buttonEl, successMsg = "Copiado!") {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      if (buttonEl) {
        const originalText = buttonEl.innerText;
        buttonEl.innerText = `✓ ${successMsg}`;
        buttonEl.classList.add("copy-success");
        setTimeout(() => {
          buttonEl.innerText = originalText;
          buttonEl.classList.remove("copy-success");
        }, 2000);
      }
      return true;
    } catch {
      return false;
    }
  }

  globalThis.CandidaturaCertaDevice = {
    isMobile,
    applyDeviceAdaptation,
    copyToClipboard
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyDeviceAdaptation);
  } else {
    applyDeviceAdaptation();
  }
  window.addEventListener("resize", applyDeviceAdaptation);
})();
