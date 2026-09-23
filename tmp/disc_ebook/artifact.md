# Template contract — DISC Hackeado

## Reference

- Visual reference: `C:\agente_curriculos\livro_disc\DISC_Hackeado.docx`
- Reference SHA-256: `F17B501677622090B97FE8E6CFC5102CEE8F315096549C27BADE5BE0AB5C1361`
- Reference render: `C:\agente_curriculos\livro_disc\qa_render` (45 pages)
- Content source: `C:\Users\xucla\Documents\O Código por Trás do DISC versao semi.docx` (25 pages, one A4 section)
- Supplemental content: `C:\Users\xucla\Documents\pasted1-text`, `C:\Users\xucla\Documents\pasted-text.txt`, and the latest CTA attachment.

## Page system

- Cover: Letter portrait, 8.5 x 11 in, zero margins, one full-page inline image.
- Body: Letter portrait, margins L/R 0.88 in, T 0.82 in, B 0.78 in; footer 0.35 in; page numbering centered.
- The cover has no page number. Body begins in a new section.
- New cards are permitted as cloned full-page patterns in their own zero-margin Letter sections, followed by the CTA as the last page.

## Typography and palette

- Existing narrative pages preserve the reference style system: Aptos body, strong navy headings, acid-green rules/callouts, pale gray-green table fills, generous paragraph rhythm.
- Cover is preserve-only: `cover_disc.png`, dark terminal aesthetic, white + acid green typography.
- New card pages follow the explicit user override: Montserrat ExtraBold/Bold for display text; Inter Regular/Bold/Italic for body; background `#0D0D0D`; white `#FFFFFF`; acid green `#00FF88`; gray `#B0B0B0`; panel `#1A1A1A`.
- Card body type must never be smaller than 18 pt. Acid green is reserved for headings, key labels, and 30% phrases.

## Components

- Preserve the existing cover artwork and full narrative content order.
- Preserve TOC, heading hierarchy, numbered/bulleted lists, tables, callouts, and centered footer page number on narrative pages.
- Replace the prior compact cards appendix with a 12-page visual cards module: module cover; how-to; D; I; S; C; DC; ID; IS; CS; consultation table; module back cover.
- Final ebook CTA remains the last page after the cards module.

## Content flow

1. Main cover.
2. Opening hook.
3. About the author.
4. Preface and introduction.
5. Chapter 0 diagnostic.
6. Chapters 1–9 with Camila/Rafael/Juliana cases interleaved.
7. Chapters 10–11, FAQ, conclusion, checklists, and commented simulation.
8. Twelve-page cards module.
9. Final CTA.

## Slot map

- Preserve: main cover, all narrative sections, cases, FAQ, conclusion, checklists, simulation, footer/page numbering.
- Rewrite: cards appendix only, using the explicit 12-page visual specification.
- Preserve/relocate: final CTA; it must remain after the cards module.
- Do not include editorial planning tables, sales-page copy, Canva setup instructions, or “where to insert” notes as reader-facing ebook content.

## Package and fidelity gates

- Preserve `cover_disc.png` byte-for-byte and reuse it as the first page.
- No text clipping, overlaps, broken tables, missing glyphs, or accidental blank pages.
- All 12 card pages must have uniform margins, titles, list rhythm, panel treatment, and page numbering.
- Render every final page and inspect at 100% before delivery.
- Accept intentional pagination and section-count changes caused by the new 12-page module.
