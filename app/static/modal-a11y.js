(function () {
  const focusable = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const openerByDialog = new WeakMap();
  const dialogSelector = 'dialog, .dialog[role="dialog"]';

  function focusInside(dialog) {
    const first = dialog.querySelector(focusable);
    (first || dialog).focus();
  }

  function restore(dialog) {
    const opener = openerByDialog.get(dialog);
    if (opener && document.contains(opener)) opener.focus();
    openerByDialog.delete(dialog);
  }

  if (window.HTMLDialogElement) {
    const originalShowModal = HTMLDialogElement.prototype.showModal;
    const originalClose = HTMLDialogElement.prototype.close;
    HTMLDialogElement.prototype.showModal = function () {
      openerByDialog.set(this, document.activeElement);
      this.setAttribute('aria-modal', 'true');
      if (!this.hasAttribute('tabindex')) this.setAttribute('tabindex', '-1');
      originalShowModal.call(this);
      requestAnimationFrame(() => focusInside(this));
    };
    HTMLDialogElement.prototype.close = function (value) {
      originalClose.call(this, value);
      requestAnimationFrame(() => restore(this));
    };
  }

  const observer = new MutationObserver((records) => {
    records.forEach((record) => {
      if (record.type !== 'attributes' || record.attributeName !== 'class') return;
      const dialog = record.target;
      if (!(dialog instanceof HTMLElement)) return;
      const isOpen = dialog.matches('.dialog.open');
      if (isOpen) {
        openerByDialog.set(dialog, document.activeElement);
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        if (!dialog.hasAttribute('tabindex')) dialog.setAttribute('tabindex', '-1');
        requestAnimationFrame(() => focusInside(dialog));
      } else if (dialog.getAttribute('role') === 'dialog') {
        requestAnimationFrame(() => restore(dialog));
      }
    });
  });
  observer.observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['class'] });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const dialog = event.target.closest?.(dialogSelector);
    if (!dialog || (dialog instanceof HTMLDialogElement && !dialog.open) || !dialog.classList.contains?.('open') && !(dialog instanceof HTMLDialogElement)) return;
    const items = [...dialog.querySelectorAll(focusable)];
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
})();
