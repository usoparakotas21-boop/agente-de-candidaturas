(function () {
  'use strict';
  function stripMarkdown(value) {
    let text = String(value || '');
    text = text.replace(/```(?:\w+)?\s*/g, '').replace(/```/g, '');
    text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
    text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
    text = text.replace(/<https?:\/\/[^>]+>/g, '');
    text = text.replace(/https?:\/\/\S+/g, '');
    text = text.replace(/^\s{0,3}#{1,6}\s*/gm, '');
    text = text.replace(/^\s*[-*+]\s+/gm, '');
    text = text.replace(/^\s*\d+[.)]\s+/gm, '');
    text = text.replace(/[*_~`]+/g, '');
    text = text.replace(/<[^>]+>/g, '');
    return text.replace(/\s+/g, ' ').trim();
  }
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function inlineMarkdown(value) {
    let text = escapeHtml(value);
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    text = text.replace(/_([^_]+)_/g, '<em>$1</em>');
    return text.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  }
  function markdownToSafeHtml(markdown) {
    const lines = String(markdown || '').split(/\r?\n/);
    const output = [];
    let list = false;
    const closeList = () => { if (list) { output.push('</ul>'); list = false; } };
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) { closeList(); continue; }
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (heading) { closeList(); const level = Math.min(6, (line.match(/^#+/) || [''])[0].length); output.push(`<h${level}>${inlineMarkdown(heading[1])}</h${level}>`); continue; }
      const bullet = line.match(/^[-*+]\s+(.+)$/) || line.match(/^\d+[.)]\s+(.+)$/);
      if (bullet) { if (!list) { output.push('<ul>'); list = true; } output.push(`<li>${inlineMarkdown(bullet[1])}</li>`); continue; }
      closeList(); output.push(`<p>${inlineMarkdown(line)}</p>`);
    }
    closeList();
    return output.join('');
  }
  window.CandidaturaText = { stripMarkdown, markdownToSafeHtml };
})();
