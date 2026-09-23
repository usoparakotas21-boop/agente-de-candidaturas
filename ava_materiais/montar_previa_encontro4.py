from pathlib import Path
from html import escape
import base64
import re

root = Path(r'C:\agente_curriculos\ava_materiais')
source = root / 'previa_encontros_II_III_IV.md'
text = source.read_text(encoding='utf-8-sig')
report = ('O quarto encontro aconteceu em 29 de agosto, pela manhã, no polo Uninter Centro Lapad, em Salvador. '
'A atividade foi dedicada à montagem e à experimentação do jogo Mestre das Respostas. '
'Os participantes trabalharam em uma mesa compartilhada, com folhas impressas, papelão, papéis coloridos, tesoura e cola. '
'Os registros mostram o recorte dos materiais, a preparação das peças e os tabuleiros organizados para o jogo. '
'O conjunto inclui uma roleta de letras, cartas de categorias, marcadores e um dado de papel com comandos de avanço e recuo. '
'A cada rodada, é preciso encontrar uma palavra que corresponda à categoria escolhida e à letra sorteada. '
'Quem responde corretamente primeiro e sinaliza a resposta pode lançar o dado. '
'Como o resultado pode indicar um recuo, a dinâmica também permite trabalhar a espera e a maneira de lidar com a frustração. '
'Na alfabetização, o jogo oferece oportunidades para explorar letras iniciais e ampliar o vocabulário. '
'O professor pode adaptar as categorias à turma e ajudar na conferência das respostas, valorizando a participação e o respeito entre os colegas.')
start = text.index('O quarto encontro aconteceu')
end = text.index('\n\n### Registros fotográficos', start)
text = text[:start] + report + text[end:]
text = text.replace('Incluir de 3 a 5 fotos reais de diferentes momentos, acompanhadas da identificação de cada etapa para as legendas.', 'Três fotografias recebidas: recorte e montagem dos materiais; organização do jogo na mesa; registro do grupo com os tabuleiros e componentes preparados.', 1)
text = text.replace('As fotos e suas legendas serão acrescentadas depois.', 'As três fotos de cada encontro foram incluídas nas prévias individuais, com legendas.')
source.write_text(text, encoding='utf-8')
part = text.split('## Encontro 04 do roteiro\n', 1)[1].split('## Informações necessárias', 1)[0]
plan = part.split('### Plano de aula\n', 1)[1].split('**Comentário proposto', 1)[0].strip()
def inline(s):
    s = escape(s)
    s = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.*?)\*', r'<em>\1</em>', s)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
plan_html = '\n'.join('<p>' + inline(p.replace('\n', ' ')) + '</p>' for p in plan.split('\n\n'))
photos = [
    ('f995c834-6e34-4ee6-9ab3-2f619788957b.jpg', 'Foto 1. Recorte e montagem dos componentes do jogo na mesa compartilhada, com folhas impressas, papelão, tesoura e cola.'),
    ('6da55d53-02a5-4939-bbf1-2bac6aaa5c6e.jpg', 'Foto 2. Organização do jogo na mesa, com tabuleiro, roleta de letras, cartas, marcadores e dados de papel.'),
    ('ada6ac2e-1469-4542-9959-2602254e7eec.jpg', 'Foto 3. Registro do grupo com os tabuleiros e os componentes preparados para a atividade.')
]
figs = []
for name, caption in photos:
    photo = Path(r'C:\Users\xucla\Documents\CAMILA\uninter') / name
    uri = 'data:image/jpeg;base64,' + base64.b64encode(photo.read_bytes()).decode('ascii')
    figs.append(f'<figure><img src="{uri}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
previous = (root / 'Encontro_II_Camila_previa.html').read_text(encoding='utf-8')
html = previous.split('<p class="relato">', 1)[0].replace('Encontro II |', 'Encontro IV |').replace('15/08/2026', '29/08/2026')
html += '<p class="relato">' + escape(report) + '</p><h2>3. REGISTROS FOTOGRÁFICOS</h2>' + ''.join(figs)
html += '<h1>PLANO DE AULA</h1>' + plan_html
html += '<footer><strong>Comentário para a postagem</strong><p>Prezado(a) professor(a), encaminho o relatório, os registros fotográficos e o plano de aula do quarto encontro do roteiro, realizado em 29/08/2026, pela manhã, no polo Uninter Centro Lapad, Salvador/BA. O trabalho apresenta o jogo Mestre das Respostas e uma proposta de letras iniciais e vocabulário para o 2º ano do Ensino Fundamental. Atenciosamente, Camila Santiago.</p></footer></main></html>'
output = root / 'Encontro_IV_Camila_previa.html'
output.write_text(html, encoding='utf-8')
assert html.count('<figure>') == 3
assert 'Jogo da Borboleta' not in html
assert '15/08/2026' not in html
print(output)
