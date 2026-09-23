from pathlib import Path
from html import escape
import base64
import re

root = Path(r'C:\agente_curriculos\ava_materiais')
source = root / 'previa_encontros_II_III_IV.md'
text = source.read_text(encoding='utf-8-sig')
report = ('O segundo encontro aconteceu em 15 de agosto, pela manhã, no polo Uninter Centro Lapad, em Salvador. '
'A atividade foi dedicada à confecção e à experimentação do Jogo da Borboleta. '
'Os participantes ficaram reunidos em uma mesa, com os materiais ao alcance e as orientações da aula exibidas na televisão. '
'Foram utilizados tabuleiros em papel, peças circulares coloridas, lápis de cor, tesoura e cola. '
'Os registros mostram a preparação dos materiais, a pintura do tabuleiro e a organização das peças para a partida em dupla. '
'O jogo propõe capturar as peças do adversário, observando os caminhos disponíveis e as regras de movimentação. '
'Na partida, cada escolha exige atenção, pois um movimento pode abrir espaço para uma captura. '
'A proposta ajuda a trabalhar o planejamento e a revisão das jogadas. '
'Para a prática docente, o material oferece uma forma simples de explorar o raciocínio e a localização espacial. '
'O professor pode acompanhar as escolhas e pedir que os alunos expliquem como chegaram a uma decisão, valorizando o processo de aprendizagem.')
start = text.index('O segundo encontro aconteceu')
end = text.index('\n\n### Registros fotográficos', start)
text = text[:start] + report + text[end:]
photo_intro = 'Incluir de 3 a 5 fotografias reais de diferentes momentos da prática. As legendas serão escritas conforme o conteúdo de cada imagem e sua identificação pela acadêmica.'
text = text.replace(photo_intro, 'Três fotografias recebidas e organizadas: preparação dos materiais na mesa coletiva; confecção e pintura do tabuleiro; experimentação do Jogo da Borboleta em dupla.', 1)
source.write_text(text, encoding='utf-8')
part = text.split('## Encontro II\n', 1)[1].split('## Encontro III', 1)[0]
plan = part.split('### Plano de aula\n',1)[1].split('**Comentário proposto',1)[0].strip()

def inline(s):
    s = escape(s)
    s = re.sub(r'\*\*(.*?)\*\*',r'<strong>\1</strong>',s)
    s = re.sub(r'\*(.*?)\*',r'<em>\1</em>',s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
    return s

plan_html = '\n'.join('<p>'+inline(p.replace('\n',' '))+'</p>' for p in plan.split('\n\n'))
photos = [
    (r'C:\Users\xucla\Documents\CAMILA\uninter\bbae3fcd-80ad-4dc3-a2ce-4696e6bea65e.jpg', 'Foto 1. Organização dos participantes e dos materiais na mesa coletiva, com a aula exibida na televisão.'),
    (r'C:\Users\xucla\Documents\CAMILA\uninter\e54db192-f0d0-496e-8ca7-1eef33916469 (1).jpg', 'Foto 2. Confecção e pintura do tabuleiro, com as peças e os materiais de apoio sobre a mesa.'),
    (r'C:\Users\xucla\Documents\CAMILA\uninter\0bbb5021-0116-4b1a-bb7a-74b8c4692efc.jpg', 'Foto 3. Experimentação do Jogo da Borboleta em dupla, com as peças posicionadas no tabuleiro.')
]
figs = []
for path, caption in photos:
    uri = 'data:image/jpeg;base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')
    figs.append(f'<figure><img src="{uri}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
html = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Encontro II | Camila Santiago</title>
<style>body{margin:0;background:#eee;color:#171717;font:16px/1.55 Arial,sans-serif}main{max-width:800px;margin:28px auto;padding:48px;background:white}h1{text-align:center;font-size:23px;margin:0 0 30px}h2{font-size:17px;background:#eee;padding:8px 10px;margin:30px 0 16px}p{margin:0 0 13px}.relato{text-align:justify}figure{margin:24px 0 34px;break-inside:avoid;text-align:center}img{max-width:100%;max-height:640px;object-fit:contain}figcaption{font-size:14px;text-align:left;margin-top:8px}a{color:#225d84}footer{border-top:1px solid #ccc;margin-top:36px;padding-top:16px;font-size:14px}@media(max-width:600px){main{margin:0;padding:22px}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}figure{page-break-inside:avoid}h2{break-after:avoid}a{color:inherit;text-decoration:none}@page{size:A4;margin:2cm}}</style>
<main><h1>RELATÓRIO DE PRÁTICA</h1><h2>1. IDENTIFICAÇÃO</h2>
<p><strong>Nome:</strong> Camila Santiago &nbsp; <strong>RU:</strong> 4958363<br><strong>Curso:</strong> Pedagogia<br><strong>Polo EaD:</strong> Uninter Centro Lapad<br><strong>Cidade e UF:</strong> Salvador/BA<br><strong>Data do encontro:</strong> 15/08/2026, pela manhã</p>
<h2>2. RELATÓRIO DA PRÁTICA REALIZADA NO LABORATÓRIO DIDÁTICO DAS LICENCIATURAS</h2>
'''
html += '<p class="relato">'+escape(report)+'</p><h2>3. REGISTROS FOTOGRÁFICOS</h2>' + ''.join(figs)
html += '<h1>PLANO DE AULA</h1>'+plan_html
html += '<footer><strong>Comentário para a postagem</strong><p>Prezado(a) professor(a), encaminho o relatório, os registros fotográficos e o plano de aula do Encontro II, realizado em 15/08/2026, pela manhã, no polo Uninter Centro Lapad, Salvador/BA. O trabalho aborda o Jogo da Borboleta e uma proposta de aplicação no 5º ano do Ensino Fundamental. Atenciosamente, Camila Santiago.</p></footer></main></html>'
output = root / 'Encontro_II_Camila_previa.html'
output.write_text(html,encoding='utf-8')
print(output)
