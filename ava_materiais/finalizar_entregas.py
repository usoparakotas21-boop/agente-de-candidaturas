from pathlib import Path
import re, base64, io, html
from lxml import html as lh, etree
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

root=Path(r'C:\agente_curriculos\ava_materiais')
changes={
'5º ano do Ensino Fundamental. Adaptação pedagógica para os anos iniciais; o material original sugere principalmente o 6º ao 9º ano e permite adequação conforme a mediação docente.':'5º ano do Ensino Fundamental.',
' e ficha de registro. Acrescentar uma malha de referência ao desenho, preservando as casas e as conexões originais, com origem e eixos numerados para identificar as posições.':'.',
'registrar posições com pares de números':'descrever a posição das peças no tabuleiro',
'A atividade de localização e registro foi acrescentada ao jogo para trabalhar essa habilidade de forma explícita.':'O tabuleiro será utilizado como representação para explorar a localização das peças.',
'Plano cartesiano, coordenadas no primeiro quadrante e representação de posições no plano.':'Localização e representação de posições no plano.',
'Demonstrar a leitura das referências horizontal e vertical. Localizar três casas e registrar seus pares de números. Explicar que a malha ajuda a descrever posições, mas os movimentos continuam limitados às conexões do jogo.':'Observar as posições das peças e as conexões do tabuleiro. Localizar três casas usando referências como centro, lado direito e lado esquerdo, mantendo a mesma orientação para a dupla. Demonstrar os movimentos permitidos.',
'Partidas e registro':'Partidas e discussão',
'registram a posição inicial e a final, comparam alternativas e explicam sua decisão':'descrevem a posição inicial e a final, comparam alternativas e explicam sua decisão',
'localiza duas peças e registra um movimento permitido':'localiza duas peças e demonstra um movimento permitido',
'por observação, ficha de jogadas e atividade final individual':'por observação das jogadas e atividade final individual',
'registra corretamente os pares':'descreve com clareza a posição das peças',
'Retomar a leitura da malha com quem precisar':'Retomar as referências de localização no tabuleiro com quem precisar',
'Foto 2. Organização das cartas e dos tabuleiros durante a preparação do material na mesa compartilhada.':'Foto 2. Prática do jogo Encontre as Imagens em dupla, com a escolha das cartas e o posicionamento das peças no tabuleiro.',
'Foto 2. Organização do jogo na mesa, com tabuleiro, roleta de letras, cartas, marcadores e dados de papel.':'Foto 2. Prática do jogo Mestre das Respostas, utilizando o tabuleiro, a roleta de letras, as cartas e o dado.'
}
for file in [root/'previa_encontros_II_III_IV.md',*root.glob('Encontro_*_Camila_previa.html')]:
    t=file.read_text(encoding='utf-8-sig')
    for a,b in changes.items():t=t.replace(a,b)
    if file.name=='Encontro_III_Camila_previa.html' and 'Achei a atividade muito difícil' not in t:
        t=t.replace('Atenciosamente, Camila Santiago.</p></footer>', 'Achei a atividade muito difícil, principalmente para encontrar a posição certa das peças. Atenciosamente, Camila Santiago.</p></footer>')
    file.write_text(t,encoding='utf-8')

pdfmetrics.registerFont(TTFont('ArialLocal',r'C:\Windows\Fonts\arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialLocalBold',r'C:\Windows\Fonts\arialbd.ttf'))
pdfmetrics.registerFontFamily('ArialLocal', normal='ArialLocal',bold='ArialLocalBold',italic='ArialLocal',boldItalic='ArialLocalBold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyLocal',fontName='ArialLocal',fontSize=10.5,leading=14,spaceAfter=8,alignment=TA_JUSTIFY))
styles.add(ParagraphStyle(name='TitleLocal',fontName='ArialLocalBold',fontSize=15,leading=19,spaceAfter=15,alignment=1))
styles.add(ParagraphStyle(name='HeadLocal',fontName='ArialLocalBold',fontSize=10.5,leading=14,spaceAfter=9,spaceBefore=8,keepWithNext=True))
styles.add(ParagraphStyle(name='CaptionLocal',fontName='ArialLocal',fontSize=9,leading=12,spaceAfter=10))

def para(tag,style='BodyLocal'):
    s=etree.tostring(tag,encoding='unicode',method='html')
    s=re.sub(r'^<p[^>]*>|</p>$','',s)
    s=s.replace('<strong>','<b>').replace('</strong>','</b>').replace('<em>','<i>').replace('</em>','</i>').replace('<br/>','<br/>')
    s=s.replace('&nbsp;',' ').replace('<br>','<br/>')
    return Paragraph(s,styles[style])
def photo(fig,maxh):
    raw=base64.b64decode(fig.find('img').get('src').split(',',1)[1])
    im=PILImage.open(io.BytesIO(raw)); w,h=im.size
    ratio=min(16.5*cm/w,maxh/h)
    return [Image(io.BytesIO(raw),width=w*ratio,height=h*ratio),Spacer(1,5),Paragraph(html.escape(fig.find('figcaption').text_content()),styles['CaptionLocal'])]

for roman in ['II','III','IV']:
    soup=lh.fromstring((root/f'Encontro_{roman}_Camila_previa.html').read_text(encoding='utf-8'))
    main=soup.find('.//main')
    ps=main.findall('p')
    headings=main.findall('h2')
    story=[Paragraph('RELATÓRIO DE PRÁTICA',styles['TitleLocal']),Paragraph('1. IDENTIFICAÇÃO',styles['HeadLocal']),para(ps[0]),Paragraph(headings[1].text_content(),styles['HeadLocal']),para(ps[1]),Paragraph('3. REGISTROS FOTOGRÁFICOS',styles['HeadLocal'])]
    figs=main.findall('figure')
    story.extend(photo(figs[0],8.3*cm))
    story.append(PageBreak())
    for fig in figs[1:]:story.append(KeepTogether(photo(fig,10.4*cm)))
    story.extend([PageBreak(),Paragraph('PLANO DE AULA',styles['TitleLocal'])])
    for p in ps[2:]:story.append(para(p))
    out=root/f'Encontro_{roman}_Camila_Santiago.pdf'
    doc=SimpleDocTemplate(str(out),pagesize=(21*cm,29.7*cm),rightMargin=2*cm,leftMargin=2*cm,topMargin=1.8*cm,bottomMargin=1.8*cm)
    doc.build(story)
    comment=soup.find('.//footer/p').text_content()
    (root/f'comentario_{roman}.txt').write_text(comment,encoding='utf-8')
    print(out)


