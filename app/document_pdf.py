"""Convert the generated DOCX documents to compact, printable A4 PDFs."""

from __future__ import annotations

from html import escape
from io import BytesIO

from docx import Document as WordDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table as WordTable
from docx.text.paragraph import Paragraph as WordParagraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _safe_text(value: str) -> str:
    """Keep text supported by ReportLab's built-in Unicode-capable WinAnsi fonts."""
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2022": "*", "\u2026": "...",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u00a0": " ",
    }
    return "".join(
        replacements.get(character, character if character in "\n\r\t" or ord(character) < 256 else "?")
        for character in value
    )


def _paragraph_markup(paragraph: WordParagraph) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        text = escape(_safe_text(run.text)).replace("\n", "<br/>")
        if not text:
            continue
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        parts.append(text)
    if not parts:
        return escape(_safe_text(paragraph.text)).replace("\n", "<br/>")
    return "".join(parts)


def docx_to_pdf(content: bytes, *, title: str = "Documento") -> bytes:
    """Render DOCX paragraphs and tables as a readable A4 PDF.

    Generated Candidatura Certa documents are text and table based. This keeps
    their content and heading hierarchy when creating an attachment without
    depending on a host-installed office suite.
    """
    if not content or not content.startswith(b"PK"):
        raise ValueError("O documento fonte não é um arquivo DOCX válido.")

    word = WordDocument(BytesIO(content))
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CandidaturaBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#24364b"),
        spaceAfter=5,
        alignment=TA_LEFT,
        splitLongWords=1,
    )
    heading = ParagraphStyle(
        "CandidaturaHeading",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#173a70"),
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True,
    )
    title_style = ParagraphStyle(
        "CandidaturaTitle",
        parent=heading,
        fontSize=17,
        leading=20,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=10,
    )
    cell_style = ParagraphStyle("CandidaturaCell", parent=body, fontSize=8.5, leading=11, spaceAfter=0)
    story = []
    body_width = A4[0] - 34 * mm

    for item in word.element.body.iterchildren():
        if isinstance(item, CT_P):
            paragraph = WordParagraph(item, word)
            markup = _paragraph_markup(paragraph)
            if not markup.strip():
                story.append(Spacer(1, 3))
                continue
            style_name = str(paragraph.style.name or "").casefold()
            style = title_style if style_name == "title" else heading if style_name.startswith("heading") else body
            story.append(Paragraph(markup, style))
        elif isinstance(item, CT_Tbl):
            word_table = WordTable(item, word)
            rows = []
            for row in word_table.rows:
                cells = []
                for cell in row.cells:
                    cell_text = "<br/>".join(
                        escape(_safe_text(paragraph.text)).replace("\n", "<br/>")
                        for paragraph in cell.paragraphs
                        if paragraph.text.strip()
                    )
                    cells.append(Paragraph(cell_text or "&nbsp;", cell_style))
                if cells:
                    rows.append(cells)
            if rows:
                columns = max(len(row) for row in rows)
                table = Table(
                    rows,
                    colWidths=[body_width / columns] * columns,
                    repeatRows=1 if len(rows) > 1 else 0,
                    hAlign="LEFT",
                    splitByRow=1,
                )
                table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7e1ed")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f6fb")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.extend((table, Spacer(1, 7)))

    if not story:
        raise ValueError("O documento não contém conteúdo que possa ser convertido.")

    output = BytesIO()
    safe_title = _safe_text(title)[:200]

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dce5ef"))
        canvas.setLineWidth(0.5)
        canvas.line(17 * mm, 13 * mm, A4[0] - 17 * mm, 13 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(17 * mm, 8 * mm, safe_title)
        canvas.drawRightString(A4[0] - 17 * mm, 8 * mm, f"{document.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        title=safe_title,
        author="Candidatura Certa",
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=16 * mm,
        bottomMargin=19 * mm,
    )
    pdf.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output.getvalue()
