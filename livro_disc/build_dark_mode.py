from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "output" / "docx" / "DISC_Hackeado_Edicao_Completa.docx"
COVER = ROOT / "cover_disc.png"
CARD_RENDER = ROOT.parent / "tmp" / "disc_ebook" / "cards_render"

NAVY = "7CFF6B"
INK = "E6E9ED"
GREEN = "7CFF6B"
MUTED = "B6BEC8"
LIGHT = "080C12"
RULE = "12241E"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def between(text: str, start: str, end: str | None = None) -> str:
    a = text.index(start)
    b = text.index(end, a + len(start)) if end else len(text)
    return text[a:b].strip()


def make_manuscript() -> str:
    main = read("manuscrito_principal.md")
    extra = read("adicoes.md")
    author = read("pacote_autor.md")

    parts = [
        between(extra, "## Você Perdeu Uma Vaga", "# CAPÍTULO 0").replace("## Você Perdeu", "# Você Perdeu", 1),
        between(author, "## Sobre o Autor", "## Versão curta").replace("## Sobre o Autor", "# Sobre o Autor", 1),
        between(main, "# Prefácio", "# Introdução"),
        between(main, "# Introdução", "# Capítulo 1:"),
        between(extra, "# CAPÍTULO 0", "# CASOS NARRADOS"),
        between(main, "# Capítulo 1:", "# Capítulo 2:"),
        between(main, "# Capítulo 2:", "# Capítulo 3:"),
        between(extra, "## Caso 1:", "## Caso 2:").replace("## Caso 1:", "# Caso 1:", 1),
        between(main, "# Capítulo 3:", "# Capítulo 4:"),
        between(main, "# Capítulo 4:", "# Capítulo 5:"),
        between(main, "# Capítulo 5:", "# Capítulo 6:"),
        between(extra, "## Caso 2:", "## Caso 3:").replace("## Caso 2:", "# Caso 2:", 1),
        between(main, "# Capítulo 6:", "# Capítulo 7:"),
        between(main, "# Capítulo 7:", "# Capítulo 8:"),
        between(main, "# Capítulo 8:", "# Capítulo 9:"),
        between(main, "# Capítulo 9:", "# Conclusão:"),
        between(extra, "## Caso 3:", "# CAPÍTULO 10").replace("## Caso 3:", "# Caso 3:", 1),
        between(extra, "# CAPÍTULO 10", "# CAPÍTULO 11"),
        between(extra, "# CAPÍTULO 11", "# FAQ"),
        between(extra, "# FAQ", "# CHECKLISTS"),
        between(main, "# Conclusão:", "# Bônus:"),
        between(extra, "# CHECKLISTS", "# SIMULADO COMENTADO"),
        between(extra, "# SIMULADO COMENTADO", "# CARDS DE BOLSO"),
    ]
    return "\n\n---\n\n".join(parts)


def font_path(candidates: list[str]) -> str:
    for p in candidates:
        if Path(p).exists():
            return p
    raise FileNotFoundError(candidates[0])


def make_cover() -> None:
    w, h = 1275, 1650
    img = Image.new("RGB", (w, h), "#080C12")
    d = ImageDraw.Draw(img)
    bold = font_path([r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf"])
    reg = font_path([r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\calibri.ttf"])
    mono = font_path([r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf"])
    title = ImageFont.truetype(bold, 116)
    sub = ImageFont.truetype(reg, 39)
    small = ImageFont.truetype(reg, 28)
    code = ImageFont.truetype(mono, 23)

    for y in range(120, 1450, 52):
        alpha = max(18, 80 - y // 32)
        color = (18, 36 + alpha // 3, 30)
        d.text((70, y), "01  D  //  I  //  S  //  C  10", font=code, fill=color)

    d.rectangle((72, 225, 92, 1055), fill="#7CFF6B")
    d.text((140, 345), "DISC", font=title, fill="#FFFFFF")
    d.text((140, 475), "HACKEADO", font=title, fill="#7CFF6B")
    d.line((142, 625, 1085, 625), fill="#7CFF6B", width=4)
    d.multiline_text(
        (145, 685),
        "O Manual Que Ninguém\nQueria Que Você Lesse",
        font=sub,
        fill="#E6E9ED",
        spacing=16,
    )
    d.text((145, 1330), "POR QUEM APLICOU 10 ANOS DE TESTES", font=small, fill="#B6BEC8")
    d.text((145, 1375), "DO OUTRO LADO DA MESA", font=small, fill="#B6BEC8")
    img.save(COVER, quality=96)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=100, start=130, bottom=100, end=130) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


_NEXT_ABSTRACT_ID = 2000
_NEXT_NUM_ID = 1000


def create_numbering_instance(doc: Document, start_at: int = 1) -> int:
    global _NEXT_ABSTRACT_ID, _NEXT_NUM_ID
    numbering = doc.part.numbering_part.element
    abstract_id = _NEXT_ABSTRACT_ID
    num_id = _NEXT_NUM_ID
    _NEXT_ABSTRACT_ID += 1
    _NEXT_NUM_ID += 1
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), str(start_at))
    lvl.append(start)
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "decimal")
    lvl.append(num_fmt)
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "%1.")
    lvl.append(lvl_text)
    suff = OxmlElement("w:suff")
    suff.set(qn("w:val"), "tab")
    lvl.append(suff)
    p_pr = OxmlElement("w:pPr")
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), "540")
    tabs.append(tab)
    p_pr.append(tabs)
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "540")
    ind.set(qn("w:hanging"), "260")
    p_pr.append(ind)
    lvl.append(p_pr)
    abstract.append(lvl)
    numbering.append(abstract)
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abs_ref = OxmlElement("w:abstractNumId")
    abs_ref.set(qn("w:val"), str(abstract_id))
    num.append(abs_ref)
    numbering.append(num)
    return num_id



def create_bullet_numbering_instance(doc: Document) -> int:
    global _NEXT_ABSTRACT_ID, _NEXT_NUM_ID
    numbering = doc.part.numbering_part.element
    abstract_id = _NEXT_ABSTRACT_ID
    num_id = _NEXT_NUM_ID
    _NEXT_ABSTRACT_ID += 1
    _NEXT_NUM_ID += 1
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    lvl.append(start)
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "bullet")
    lvl.append(num_fmt)
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "•")
    lvl.append(lvl_text)
    p_pr = OxmlElement("w:pPr")
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "540")
    ind.set(qn("w:hanging"), "260")
    p_pr.append(ind)
    lvl.append(p_pr)
    r_pr = OxmlElement("w:rPr")
    r_fonts = OxmlElement("w:rFonts")
    r_fonts.set(qn("w:ascii"), "Montserrat")
    r_fonts.set(qn("w:hAnsi"), "Montserrat")
    r_pr.append(r_fonts)
    lvl.append(r_pr)
    abstract.append(lvl)
    numbering.append(abstract)
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abs_ref = OxmlElement("w:abstractNumId")
    abs_ref.set(qn("w:val"), str(abstract_id))
    num.append(abs_ref)
    numbering.append(num)
    return num_id

def apply_numbering(paragraph, num_id: int) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        p_pr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_ref = OxmlElement("w:numId")
    num_ref.set(qn("w:val"), str(num_id))
    num_pr.extend([ilvl, num_ref])

def set_fixed_table_geometry(table, widths_dxa: list[int]) -> None:
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths_dxa)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            tc_w = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tc_w)
            tc_w.set(qn("w:w"), str(widths_dxa[idx]))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(widths_dxa[idx] / 1440)
            set_cell_margins(cell)


def set_run_font(run, size=None, bold=None, italic=None, color=None, name="Montserrat") -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


INLINE = re.compile(r"(\*\*.*?\*\*|\*.*?\*|`.*?`)")


def add_inline(paragraph, text: str, base_color=INK) -> None:
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            set_run_font(paragraph.add_run(text[pos:m.start()]), color=base_color)
        token = m.group(0)
        if token.startswith("**"):
            set_run_font(paragraph.add_run(token[2:-2]), bold=True, color=base_color)
        elif token.startswith("*"):
            set_run_font(paragraph.add_run(token[1:-1]), italic=True, color=base_color)
        else:
            set_run_font(paragraph.add_run(token[1:-1]), name="Consolas", size=9.5, color=NAVY)
        pos = m.end()
    if pos < len(text):
        set_run_font(paragraph.add_run(text[pos:]), color=base_color)


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_begin, instr, fld_end])
    set_run_font(run, size=9, color=MUTED)



def apply_dark_mode(doc: Document) -> None:
    background = OxmlElement("w:background")
    background.set(qn("w:color"), "080C12")
    doc.element.insert(0, background)
    
    display_background = OxmlElement("w:displayBackgroundShape")
    doc.settings.element.append(display_background)

def set_row_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "true")
    tr_pr.append(cant_split)

def configure_styles(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Montserrat"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Montserrat")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Montserrat")
    normal.font.size = Pt(10.8)
    normal.font.color.rgb = RGBColor.from_string(INK)
    pf = normal.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.space_after = Pt(6)
    pf.line_spacing = 1.20

    specs = {
        "Title": (32, "FFFFFF", 0, 12),
        "Subtitle": (15, MUTED, 0, 10),
        "Heading 1": (20, NAVY, 0, 12),
        "Heading 2": (15, NAVY, 16, 7),
        "Heading 3": (12.5, "B6BEC8", 12, 5),
    }
    for name, (size, color, before, after) in specs.items():
        st = styles[name]
        st.font.name = "Montserrat" if name != "Normal" else "Montserrat"
        st._element.rPr.rFonts.set(qn("w:ascii"), st.font.name)
        st._element.rPr.rFonts.set(qn("w:hAnsi"), st.font.name)
        st.font.size = Pt(size)
        st.font.bold = name != "Subtitle"
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True
        st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    for name in ("List Bullet", "List Number"):
        st = styles[name]
        st.font.name = "Montserrat"
        st.font.size = Pt(10.6)
        st.paragraph_format.left_indent = Inches(0.38)
        st.paragraph_format.first_line_indent = Inches(-0.19)
        st.paragraph_format.space_after = Pt(4)
        st.paragraph_format.line_spacing = 1.2

    if "Quote Box" not in styles:
        q = styles.add_style("Quote Box", WD_STYLE_TYPE.PARAGRAPH)
    else:
        q = styles["Quote Box"]
    q.font.name = "Montserrat"
    q.font.size = Pt(10.5)
    q.font.italic = True
    q.font.color.rgb = RGBColor.from_string("315B4B")
    q.paragraph_format.left_indent = Inches(0.28)
    q.paragraph_format.right_indent = Inches(0.18)
    q.paragraph_format.space_before = Pt(5)
    q.paragraph_format.space_after = Pt(8)


def parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def add_markdown(doc: Document, md: str) -> None:
    lines = md.splitlines()
    i = 0
    first_h1 = True
    active_num_id = None
    bullet_num_id = create_bullet_numbering_instance(doc)
    while i < len(lines):
        raw = lines[i].rstrip()
        line = raw.strip()
        if not line or line == "---":
            active_num_id = None
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            active_num_id = None
            block = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = parse_table(block)
            if rows:
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                table.alignment = WD_TABLE_ALIGNMENT.LEFT
                table.style = "Table Grid"
                n = len(rows[0])
                widths = [9360 // n] * n
                widths[-1] += 9360 - sum(widths)
                set_fixed_table_geometry(table, widths)
                for r, values in enumerate(rows):
                    for c, value in enumerate(values):
                        cell = table.cell(r, c)
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        p = cell.paragraphs[0]
                        p.paragraph_format.space_after = Pt(0)
                        add_inline(p, value, NAVY if r == 0 else INK)
                        if r == 0:
                            set_cell_shading(cell, "111827")
                            for run in p.runs:
                                run.bold = True
                set_repeat_table_header(table.rows[0])
                for row in table.rows:
                    set_row_cant_split(row)
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            active_num_id = None
            level = len(m.group(1))
            text = m.group(2)
            page_break_before = level == 1 and not first_h1
            if level == 1:
                first_h1 = False
            p = doc.add_paragraph(style=f"Heading {level}")
            if page_break_before:
                p.paragraph_format.page_break_before = True
            add_inline(p, text, NAVY)
            i += 1
            continue
        if line.startswith(">"):
            active_num_id = None
            p = doc.add_paragraph(style="Quote Box")
            add_inline(p, line.lstrip("> "))
            i += 1
            continue
        if re.match(r"^[-*]\s+", line):
            active_num_id = None
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.28)
            p.paragraph_format.first_line_indent = Inches(-0.18)
            add_inline(p, "• " + re.sub(r"^[-*]\s+", "", line))
            i += 1
            continue
        numbered = re.match(r"^(\d+)[.)]\s+", line)
        if numbered:
            active_num_id = None
            content = re.sub(r"^\d+[.)]\s+", "", line)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.28)
            p.paragraph_format.first_line_indent = Inches(-0.18)
            add_inline(p, f"{numbered.group(1)}. " + content)
            i += 1
            continue
        active_num_id = None
        para_lines = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt == "---" or re.match(r"^(#{1,3})\s+", nxt) or nxt.startswith(">") or re.match(r"^[-*]\s+", nxt) or re.match(r"^\d+[.)]\s+", nxt) or nxt.startswith("|"):
                break
            para_lines.append(nxt)
            i += 1
        p = doc.add_paragraph()
        add_inline(p, " ".join(para_lines))

def add_static_toc(doc: Document, md: str) -> None:
    doc.add_paragraph("Sumário", style="Heading 1")
    for line in md.splitlines():
        m = re.match(r"^(#|##)\s+(.*)$", line.strip())
        if not m:
            continue
        label = re.sub(r"[*`]+", "", m.group(2)).strip()
        if len(m.group(1)) == 1:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0)
            p.paragraph_format.space_after = Pt(3)
            r = p.add_run(label)
            set_run_font(r, size=10.5, bold=True, color=NAVY)
        elif re.match(r"^(\d+\.\d+|O que|Como|A |As |E |Antes|Perguntas|Checklist|Treine|CARD)", label, re.I):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.28)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(label)
            set_run_font(r, size=9.5, color=MUTED)
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run("Cards de Bolso DISC")
    set_run_font(r, size=10.5, bold=True, color=NAVY)
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.28)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("8 cards + consulta rápida + CTA final")
    set_run_font(r, size=9.5, color=MUTED)
    doc.add_page_break()


def add_card_module(doc: Document) -> None:
    pages = [CARD_RENDER / f"card-{i:02d}.png" for i in range(1, 13)]
    missing = [str(page) for page in pages if not page.exists()]
    if missing:
        raise FileNotFoundError("Páginas dos cards ausentes: " + ", ".join(missing))

    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.page_width = Mm(210)
    sec.page_height = Mm(297)
    sec.top_margin = Mm(0)
    sec.bottom_margin = Mm(0)
    sec.left_margin = Mm(0)
    sec.right_margin = Mm(0)
    sec.header_distance = Mm(0)
    sec.footer_distance = Mm(0)
    sec.header.is_linked_to_previous = False
    sec.footer.is_linked_to_previous = False
    sec.header.paragraphs[0].clear()
    sec.footer.paragraphs[0].clear()

    for idx, image_path in enumerate(pages, start=1):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.left_indent = Mm(0)
        p.paragraph_format.right_indent = Mm(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1
        shape = p.add_run().add_picture(str(image_path), width=Mm(210), height=Mm(296.2))
        shape._inline.docPr.set("title", f"Cards de Bolso DISC — página {idx}")
        shape._inline.docPr.set("descr", "Página visual em fundo escuro com tipografia Montserrat e Inter, acentos em verde-ácido e conteúdo de consulta rápida DISC.")
        if idx < len(pages):
            p.add_run().add_break(WD_BREAK.PAGE)


def build(mode: str = "bundle") -> None:
    md = make_manuscript()
    if mode == "preview":
        try:
            md = md.split("# Capítulo 3:")[0].strip()
        except:
            pass
        OUT = ROOT.parent / "output" / "docx" / "Preview_DISC_Hackeado.docx"
    elif mode == "livro":
        md = md.split("# CARDS DE BOLSO")[0].strip()
        OUT = ROOT.parent / "output" / "docx" / "DISC_Hackeado.docx"
    else:
        OUT = ROOT.parent / "output" / "docx" / "DISC_Hackeado_Edicao_Completa.docx"

    (ROOT / "manuscrito_montado.md").write_text(md, encoding="utf-8")
    if mode != "preview": make_cover()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    configure_styles(doc)
    apply_dark_mode(doc)
    sec = doc.sections[0]
    sec.page_width = Inches(8.5)
    sec.page_height = Inches(11)
    sec.top_margin = Inches(0)
    sec.bottom_margin = Inches(0)
    sec.left_margin = Inches(0)
    sec.right_margin = Inches(0)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.left_indent = Inches(0)
    p.paragraph_format.right_indent = Inches(0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1
    cover_shape = p.add_run().add_picture(str(COVER), width=Inches(8.5), height=Inches(10.98))
    cover_shape._inline.docPr.set("title", "DISC Hackeado")
    cover_shape._inline.docPr.set("descr", "Capa escura do livro DISC Hackeado, com título branco e verde em estética de terminal.")

    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.page_width = Inches(8.5)
    body.page_height = Inches(11)
    body.top_margin = Inches(0.82)
    body.bottom_margin = Inches(0.78)
    body.left_margin = Inches(0.88)
    body.right_margin = Inches(0.88)
    body.header_distance = Inches(0.35)
    body.footer_distance = Inches(0.35)
    body.header.is_linked_to_previous = False
    body.footer.is_linked_to_previous = False
    sec.header.paragraphs[0].clear()
    sec.footer.paragraphs[0].clear()

    pg_num = OxmlElement("w:pgNumType")
    pg_num.set(qn("w:start"), "1")
    body._sectPr.append(pg_num)

    hp = body.header.paragraphs[0]
    hp.text = "DISC HACKEADO  /  O MANUAL QUE NINGUÉM QUERIA QUE VOCÊ LESSE"
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    hp.paragraph_format.space_after = Pt(0)
    for run in hp.runs:
        set_run_font(run, size=8, bold=True, color=MUTED)
    add_page_number(body.footer.paragraphs[0])

    add_static_toc(doc, md)
    add_markdown(doc, md)
    if mode == "bundle":
        add_card_module(doc)

    core = doc.core_properties
    core.title = "DISC Hackeado"
    core.subject = "O Manual Que Ninguém Queria Que Você Lesse"
    core.author = "Autor do manuscrito"
    core.keywords = "DISC, carreira, recrutamento, seleção, comportamento"
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build("preview")
    build("livro")
    build("bundle")









