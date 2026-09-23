from __future__ import annotations

from pathlib import Path
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "Cards_de_Bolso_DISC.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

W, H = A4
BG = HexColor("#0D0D0D")
PANEL = HexColor("#171A18")
PANEL_2 = HexColor("#111111")
GREEN = HexColor("#00FF88")
TEXT = HexColor("#FFFFFF")
MUTED = HexColor("#B0B0B0")
SOFT = HexColor("#D9E1DD")
RED = HexColor("#FF6B6B")

FONT_DIR = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("Body", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("BodyBold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("BodyItalic", str(FONT_DIR / "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Display", str(FONT_DIR / "ariblk.ttf")))


CARDS = [
    {
        "code": "D", "name": "O EXECUTOR",
        "keywords": "liderança · resultado · decisão · agilidade · metas · desafios",
        "extreme": [
            "Tomo decisões difíceis mesmo sob pressão",
            "Confronto problemas de frente em vez de evitar",
            "Sou capaz de dizer 'não' sem culpa",
            "Estabeleço metas ambiciosas e me cobro pra cumpri-las",
            "Tomo iniciativa sem esperar que alguém me peça",
            "Não me incomodo em ser impopular se a decisão for certa",
            "Costumo me impor quando alguém atravessa um limite meu",
            "Tomo decisões rápidas, mas com informações",
            "Gosto de assumir liderança em projetos",
        ],
        "never": [
            "Evito riscos desnecessários → no máximo neutro",
            "Sou paciente com pessoas e processos → no máximo neutro",
            "Prefiro ambientes estáveis a mudanças → no máximo 'discordo'",
            "Coloco as necessidades dos outros antes das minhas → no máximo 'discordo'",
        ],
        "phrase": "Prefiro agir com autonomia, mas respeito o alinhamento do time.",
        "jobs": "Gerência · liderança comercial · gestão de projetos · startups · coordenadoria de operação",
    },
    {
        "code": "I", "name": "O COMUNICADOR",
        "keywords": "comunicação · trabalho em equipe · relacionamento · vendas · negociação · engajamento",
        "extreme": [
            "Conhecer pessoas novas me dá energia",
            "Sou otimista e mantenho o ânimo do grupo",
            "Inspiro pessoas a verem possibilidades que elas mesmas não viam",
            "Adoro celebrar conquistas, minhas e dos outros",
            "Me sinto à vontade no centro das atenções",
            "Tenho facilidade pra conversar com qualquer um",
            "Conto histórias e experiências pessoais pra explicar minha visão",
            "Estimulo pessoas mais quietas a se expressarem",
            "Prefiro trabalhar em equipe a sozinho",
        ],
        "never": [
            "Prefiro seguir procedimentos estabelecidos → no máximo neutro",
            "Confio mais em lógica do que em intuição → no máximo neutro",
            "Presto atenção em detalhes que outros não percebem → no máximo neutro",
            "Prefiro trabalhar sozinho → no máximo 'discordo'",
        ],
        "phrase": "Sou energético, mas tenho disciplina pra entregar sozinho quando necessário.",
        "jobs": "Vendas · marketing · recrutamento · relações públicas · customer success · atendimento consultivo",
    },
    {
        "code": "S", "name": "O PLANEJADOR",
        "keywords": "rotina · estabilidade · trabalho em equipe · paciência · consistência · atendimento",
        "extreme": [
            "Prefiro ambientes estáveis a mudanças constantes",
            "Sou paciente com pessoas e processos",
            "Mantenho a calma mesmo sob estresse",
            "Termino o que começo, mesmo quando fica difícil",
            "Sou alguém em quem as pessoas confiam pra desabafar",
            "Tenho facilidade pra ouvir o outro sem interromper",
            "Adapto-me melhor quando tenho tempo pra processar",
            "Considero como minhas decisões afetam quem está perto",
            "Prefiro mudanças graduais a transformações abruptas",
        ],
        "never": [
            "Gosto de competir pra vencer → no máximo neutro",
            "Falo direto mesmo que incomode → no máximo 'discordo'",
            "Sou capaz de dizer 'não' sem culpa → no máximo neutro",
            "Conhecer pessoas novas me dá energia → no máximo neutro",
        ],
        "phrase": "Valorizo estabilidade, mas me adapto quando o contexto pede.",
        "jobs": "Suporte técnico · atendimento · operações · logística · coordenação de rotina · administração",
    },
    {
        "code": "C", "name": "O ANALISTA",
        "keywords": "precisão · análise · atenção a detalhes · qualidade · processo · dados",
        "extreme": [
            "Presto atenção em detalhes que outros não percebem",
            "Confio mais em lógica do que em intuição",
            "Sinto-me desconfortável com decisões impulsivas",
            "Valorizo qualidade acima de velocidade",
            "Analiso cuidadosamente antes de decidir",
            "Tenho facilidade em identificar falhas e erros potenciais",
            "Sigo abordagens sistemáticas pra resolver problemas",
            "Prefiro resolver problemas com fatos concretos",
            "Valorizo precisão na comunicação",
        ],
        "never": [
            "Me sinto à vontade no centro das atenções → no máximo neutro",
            "Gosto de assumir liderança → no máximo neutro",
            "Conhecer pessoas novas me dá energia → no máximo neutro",
            "Sou otimista e mantenho o ânimo do grupo → no máximo neutro",
        ],
        "phrase": "Analiso antes de decidir, mas decido com firmeza quando os dados são claros.",
        "jobs": "TI · engenharia · contabilidade · auditoria · qualidade · jurídico · análise de dados",
    },
    {
        "code": "DC", "name": "O LÍDER TÉCNICO",
        "keywords": "liderança técnica · qualidade com decisão · metas · excelência · rigor",
        "lead": "Tudo do CARD C + estas frases de D:",
        "extreme": [
            "Não me incomodo em ser impopular se a decisão for certa",
            "Estabeleço padrões altos pra mim e pra quem trabalha comigo",
            "Tomo decisões rápidas, mas com base em dados",
            "Sou direto, mas nunca displicente",
        ],
        "never": [
            "Prefiro mudanças constantes → no máximo neutro",
            "Conhecer pessoas novas me dá energia → no máximo neutro",
        ],
        "phrase": "Sou exigente com qualidade, mas reconheço prazos reais.",
        "jobs": "CTO · gerente de produto · consultoria estratégica · gestão técnica · prevenção de qualidade",
    },
    {
        "code": "ID", "name": "O LÍDER CARISMÁTICO",
        "keywords": "liderança · inspiração · comunicação · resultado · crescimento",
        "lead": "Tudo do CARD D + estas frases de I:",
        "extreme": [
            "Inspiro pessoas a verem possibilidades",
            "Sou otimista e mantenho o ânimo do grupo",
            "Adoro celebrar conquistas, minhas e dos outros",
            "Sou direto e entusiasta ao mesmo tempo",
        ],
        "never": [
            "Prefiro rotinas previsíveis → no máximo neutro",
            "Confio em lógica acima de tudo → no máximo neutro",
        ],
        "phrase": "Conduzo com firmeza, mas levo o time junto.",
        "jobs": "Head de growth · fundador · líder comercial · gestão de vendas · liderança de área",
    },
    {
        "code": "IS", "name": "O ACOLHEDOR COMUNICATIVO",
        "keywords": "relacionamento · trabalho em equipe · comunicação · acolhimento · engajamento",
        "lead": "Tudo do CARD I + estas frases de S:",
        "extreme": [
            "Estimulo pessoas mais quietas a se expressarem",
            "Sou alguém em quem as pessoas confiam pra desabafar",
            "Mantenho a calma mesmo sob estresse",
            "Considero como minhas decisões afetam quem está perto",
        ],
        "never": [
            "Gosto de competir pra vencer → no máximo neutro",
            "Falo direto mesmo que incomode → no máximo neutro",
        ],
        "phrase": "Crio ambiente confortável, mas sei cobrar quando preciso.",
        "jobs": "RH · customer success · coordenação de equipe · treinamento · desenvolvimento de pessoas",
    },
    {
        "code": "CS", "name": "O GUARDIÃO DE QUALIDADE",
        "keywords": "processo · qualidade · rotina · rigor · consistência · conformidade",
        "lead": "Tudo do CARD C + estas frases de S:",
        "extreme": [
            "Sigo abordagens sistemáticas pra resolver problemas",
            "Termino o que começo, mesmo quando fica difícil",
            "Prefiro seguir procedimentos estabelecidos",
            "Sigo o padrão porque padrão evita erro",
        ],
        "never": [
            "Gosto de competir pra vencer → no máximo neutro",
            "Me sinto à vontade no centro das atenções → no máximo neutro",
        ],
        "phrase": "Sigo processos porque eles evitam erro - não por rigidez.",
        "jobs": "Auditoria · compliance · engenharia de qualidade · contabilidade · DP · administração de pessoal",
    },
]


def background(c: canvas.Canvas, page_no: int | None = None) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#183328"))
    c.setLineWidth(0.35)
    for x in range(0, int(W), 32):
        c.line(x, 0, x, H)
    for y in range(0, int(H), 32):
        c.line(0, y, W, y)
    c.setFillColor(BG)
    c.roundRect(22, 22, W - 44, H - 44, 12, fill=1, stroke=0)
    if page_no is not None:
        c.setFont("Body", 8)
        c.setFillColor(MUTED)
        c.drawRightString(W - 34, 24, f"{page_no:02d} / 12")


def fit_lines(text: str, font: str, size: float, width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if pdfmetrics.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrapped(c, text, x, y, width, font="Body", size=11, color=TEXT, leading=None, max_lines=None):
    leading = leading or size * 1.35
    lines = fit_lines(text, font, size, width)
    if max_lines:
        lines = lines[:max_lines]
    c.setFont(font, size)
    c.setFillColor(color)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def section_label(c, text, y, color=GREEN):
    c.setFont("BodyBold", 13)
    c.setFillColor(color)
    c.drawString(46, y, text)
    return y - 22


def list_items(c, items, y, width=500, size=10.3, color=TEXT):
    for item in items:
        c.setFillColor(GREEN)
        c.circle(52, y + 3, 2.5, fill=1, stroke=0)
        y = wrapped(c, f'"{item}"', 64, y, width - 18, "Body", size, color, size * 1.32)
        y -= 3
    return y


def title_block(c, code, name, keywords, page_no):
    c.setFillColor(GREEN)
    c.roundRect(42, H - 112, 72, 72, 12, fill=1, stroke=0)
    c.setFillColor(BG)
    c.setFont("Display", 27 if len(code) == 1 else 23)
    c.drawCentredString(78, H - 88, code)
    c.setFillColor(TEXT)
    c.setFont("Display", 25 if len(name) < 20 else 21)
    c.drawString(130, H - 75, f"CARD {code}")
    c.setFillColor(GREEN)
    c.setFont("BodyBold", 16)
    c.drawString(130, H - 101, name)
    c.setFont("BodyItalic", 9.6)
    c.setFillColor(MUTED)
    wrapped(c, "A vaga que pede esse perfil fala: " + keywords, 46, H - 137, W - 92, "BodyItalic", 9.6, MUTED, 12)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.4)
    c.line(46, H - 159, W - 46, H - 159)
    return H - 190


def card_page(c, data, page_no):
    background(c, page_no)
    y = title_block(c, data["code"], data["name"], data["keywords"], page_no)
    y = section_label(c, "PONTUE NO EXTREMO  |  concordo plenamente / sempre", y)
    if data.get("lead"):
        y = wrapped(c, data["lead"], 46, y, W - 92, "BodyBold", 10.8, SOFT, 14) - 5
    item_size = 10.2 if len(data["extreme"]) >= 8 else 11.2
    y = list_items(c, data["extreme"], y, W - 92, item_size)
    y -= 6
    y = section_label(c, "NUNCA PONTUE NO EXTREMO", y, RED)
    y = list_items(c, data["never"], y, W - 92, 10.1, SOFT)
    y -= 5
    box_h = 70
    c.setFillColor(PANEL)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.2)
    c.roundRect(42, y - box_h + 8, W - 84, box_h, 9, fill=1, stroke=1)
    c.setFont("BodyBold", 10.5)
    c.setFillColor(GREEN)
    c.drawString(58, y - 11, "A FRASE DO 30%")
    wrapped(c, f'"{data["phrase"]}"', 58, y - 31, W - 116, "BodyItalic", 11.2, TEXT, 14)
    y -= box_h + 9
    c.setFont("BodyBold", 9.6)
    c.setFillColor(MUTED)
    c.drawString(46, y, "CARGO TÍPICO")
    wrapped(c, data["jobs"], 46, y - 17, W - 92, "Body", 9.7, SOFT, 12)
    c.showPage()


def cover(c):
    background(c)
    c.setFillColor(GREEN)
    c.rect(52, 106, 12, H - 212, fill=1, stroke=0)
    c.setFillColor(HexColor("#123D2B"))
    c.setFont("Body", 8)
    for y in range(130, int(H - 110), 23):
        c.drawString(82, y, "D // I // S // C   70 / 30")
    c.setFillColor(TEXT)
    c.setFont("Display", 39)
    c.drawString(98, H - 255, "CARDS DE BOLSO")
    c.setFillColor(GREEN)
    c.setFont("Display", 62)
    c.drawString(98, H - 329, "DISC")
    c.setStrokeColor(GREEN)
    c.setLineWidth(3)
    c.line(100, H - 357, W - 64, H - 357)
    c.setFont("BodyBold", 19)
    c.drawString(100, H - 400, "Consulte 10 minutos antes")
    c.drawString(100, H - 426, "de abrir qualquer teste")
    c.setFillColor(TEXT)
    c.setFont("Body", 12.5)
    wrapped(c, "Os 4 perfis completos. As 4 combinações que mais aparecem em vagas reais.", 100, H - 478, W - 168, "Body", 12.5, TEXT, 18)
    wrapped(c, "As frases-âncora. O que pontuar no extremo. O que nunca pontuar.", 100, H - 530, W - 168, "BodyBold", 12.5, TEXT, 18)
    c.setFillColor(MUTED)
    c.setFont("BodyItalic", 10.5)
    c.drawString(100, 93, "Por quem aplicou 10 anos de testes do outro lado da mesa.")
    c.showPage()


def how_to(c):
    background(c, 2)
    c.setFont("Display", 31)
    c.setFillColor(GREEN)
    c.drawString(46, H - 80, "COMO USAR ESTES CARDS")
    steps = [
        ("01", "LEIA A VAGA", "Abra o job description e procure as palavras-chave. Cada card tem a lista delas no início."),
        ("02", "ESCOLHA O CARD", "As palavras da vaga apontam para um perfil ou combinação. Se apontarem para duas, use a combinação."),
        ("03", "CONSULTE 10 MINUTOS ANTES", "Leia as frases-âncora do card escolhido e guarde o que pontuar, o que evitar e a frase do 30%."),
    ]
    y = H - 135
    for num, title, body in steps:
        c.setFillColor(PANEL)
        c.roundRect(42, y - 105, W - 84, 95, 10, fill=1, stroke=0)
        c.setFillColor(GREEN)
        c.setFont("Display", 23)
        c.drawString(58, y - 42, num)
        c.setFont("BodyBold", 14)
        c.drawString(112, y - 35, title)
        wrapped(c, body, 112, y - 57, W - 172, "Body", 10.8, TEXT, 14)
        y -= 117
    c.setFillColor(PANEL_2)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.4)
    c.roundRect(42, 104, W - 84, 170, 12, fill=1, stroke=1)
    c.setFillColor(GREEN)
    c.setFont("Display", 23)
    c.drawString(60, 228, "A REGRA 70 / 30")
    c.setFont("BodyBold", 16)
    c.drawString(60, 192, "70% na linguagem da vaga. 30% neutro.")
    wrapped(c, "O teste não pune quem tem perfil forte. Pune quem parece estar encenando. Responder tudo no extremo sinaliza inconsistência.", 60, 158, W - 120, "Body", 11.3, TEXT, 16)
    c.showPage()


def quick_table(c):
    background(c, 11)
    c.setFont("Display", 29)
    c.setFillColor(GREEN)
    c.drawString(46, H - 78, "CONSULTA RÁPIDA")
    c.setFont("BodyBold", 14)
    c.setFillColor(TEXT)
    c.drawString(46, H - 106, "Vaga → Card em 30 segundos")
    rows = [
        ("Liderança · metas · resultado", "D"),
        ("Comunicação · vendas · relacionamento", "I"),
        ("Rotina · paciência · atendimento", "S"),
        ("Precisão · análise · dados", "C"),
        ("Liderança técnica · qualidade com decisão", "DC"),
        ("Liderança carismática · crescimento", "ID"),
        ("RH · acolhimento · engajamento", "IS"),
        ("Processo · conformidade · consistência", "CS"),
    ]
    x, y, table_w, row_h = 46, H - 155, W - 92, 55
    c.setFillColor(GREEN)
    c.rect(x, y - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(BG)
    c.setFont("BodyBold", 11)
    c.drawString(x + 15, y - 34, "A VAGA FALA EM...")
    c.drawCentredString(x + table_w - 58, y - 34, "CARD")
    y -= row_h
    for idx, (label, code) in enumerate(rows):
        c.setFillColor(PANEL if idx % 2 else PANEL_2)
        c.rect(x, y - row_h, table_w, row_h, fill=1, stroke=0)
        c.setFillColor(TEXT)
        c.setFont("Body", 10.6)
        c.drawString(x + 15, y - 34, label)
        c.setFillColor(GREEN)
        c.setFont("Display", 15)
        c.drawCentredString(x + table_w - 58, y - 35, code)
        y -= row_h
    c.setFillColor(PANEL)
    c.setStrokeColor(GREEN)
    c.roundRect(46, 73, W - 92, 113, 10, fill=1, stroke=1)
    c.setFillColor(GREEN)
    c.setFont("BodyBold", 17)
    c.drawString(62, 146, "70% NA LINGUAGEM DA VAGA. 30% NEUTRO.")
    wrapped(c, "O teste não pune quem tem perfil forte. Pune quem parece estar encenando.", 62, 114, W - 124, "Body", 10.8, TEXT, 15)
    c.showPage()


def back_cover(c):
    background(c, 12)
    c.setFillColor(TEXT)
    c.setFont("Display", 31)
    c.drawString(54, H - 155, "O TESTE NÃO MEDE")
    c.drawString(54, H - 194, "QUEM VOCÊ É.")
    c.setFillColor(GREEN)
    c.drawString(54, H - 253, "MEDE O QUE VOCÊ")
    c.drawString(54, H - 292, "RESPONDE.")
    c.setStrokeColor(GREEN)
    c.setLineWidth(2)
    c.line(56, H - 324, W - 56, H - 324)
    wrapped(c, "A empresa já escolheu o perfil que quer antes de você abrir o questionário. Estes cards são o atalho.", 56, H - 372, W - 112, "Body", 13, TEXT, 19)
    c.setFillColor(PANEL)
    c.roundRect(52, 176, W - 104, 175, 12, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("BodyBold", 10)
    c.drawString(72, 315, "O CÓDIGO COMPLETO")
    c.setFillColor(GREEN)
    c.setFont("Display", 30)
    c.drawString(72, 272, "DISC HACKEADO")
    wrapped(c, "Simulado de 20 perguntas, Regra 70/30 detalhada e entrevista comportamental.", 72, 238, W - 144, "Body", 11, TEXT, 15)
    c.setFillColor(GREEN)
    c.roundRect(72, 188, 235, 34, 8, fill=1, stroke=0)
    c.setFillColor(BG)
    c.setFont("BodyBold", 11)
    c.drawCentredString(189, 200, "O CÓDIGO COMPLETO SAI EM BREVE")
    c.setFillColor(MUTED)
    c.setFont("BodyItalic", 9.5)
    c.drawString(56, 91, "Por quem aplicou 10 anos de testes do outro lado da mesa.")
    c.showPage()


def build():
    c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1)
    c.setTitle("Cards de Bolso DISC")
    c.setAuthor("Autor do material")
    c.setSubject("Consulta rápida dos perfis DISC")
    cover(c)
    how_to(c)
    for idx, data in enumerate(CARDS, start=3):
        card_page(c, data, idx)
    quick_table(c)
    back_cover(c)
    c.save()
    print(OUT)


if __name__ == "__main__":
    build()
