from pathlib import Path
from html import escape
import base64
import re

root = Path(r'C:\agente_curriculos\ava_materiais')
source = root / 'previa_encontros_II_III_IV.md'
text = source.read_text(encoding='utf-8-sig')
report = ('O terceiro encontro aconteceu em 22 de agosto, pela manhã, no polo Uninter Centro Lapad, em Salvador. '
'A atividade foi dedicada à preparação do jogo Encontre as Imagens. '
'Na mesa compartilhada, foram organizados os tabuleiros com figuras de animais, as cartas de desafios e os materiais para a montagem. '
'As fotos mostram o uso de folhas impressas, papéis coloridos, tesoura e cola, desde o recorte das peças até a apresentação do conjunto pronto. '
'As cartas de diferentes cores indicam os níveis de dificuldade previstos no roteiro. '
'O desafio consiste em cobrir parte do tabuleiro, deixando visíveis somente os animais e as quantidades pedidos na carta. '
'Para chegar à solução, é preciso observar, contar e experimentar posições diferentes para as peças. '
'Quando a configuração não atende ao pedido, o jogador pode reorganizá-la e conferir novamente. '
'Na aplicação com crianças, essa dinâmica permite trabalhar a contagem sem separar o conteúdo da brincadeira. '
'O professor pode acompanhar as tentativas, fazer perguntas e oferecer ajuda conforme a necessidade de cada aluno, valorizando o raciocínio e o tempo de aprendizagem.')
start = text.index('O terceiro encontro aconteceu')
end = text.index('\n\n### Registros fotográficos', start)
text = text[:start] + report + text[end:]
text = text.replace('Incluir de 3 a 5 fotos da prática, identificando os momentos retratados para a elaboração das legendas.', 'Três fotografias recebidas: recorte das peças; organização das cartas e tabuleiros na mesa compartilhada; apresentação do jogo pronto.', 1)
source.write_text(text, encoding='utf-8')
part = text.split('## Encontro III\n', 1)[1].split('## Encontro 04', 1)[0]
plan = part.split('### Plano de aula\n', 1)[1].split('**Comentário proposto', 1)[0].strip()
def inline(s):
    s = escape(s)
    s = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.*?)\*', r'<em>\1</em>', s)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
plan_html = '\n'.join('<p>' + inline(p.replace('\n', ' ')) + '</p>' for p in plan.split('\n\n'))
photos = [
    ('e47b72c5-0ea4-459a-9423-7b25d554550e.jpg', 'Foto 1. Recorte das peças do jogo, com folhas impressas, papéis coloridos, tesoura e cola sobre a mesa.'),
    ('3cdf4589-a6fa-4ab5-8843-3c378f6b6d7a.jpg', 'Foto 2. Organização das cartas e dos tabuleiros durante a preparação do material na mesa compartilhada.'),
    ('2d022cc4-38ea-4dc4-8ded-b71587843190.jpg', 'Foto 3. Apresentação do jogo Encontre as Imagens, com o tabuleiro, as cartas de desafios e as peças de cobertura.')
]
figs = []
for name, caption in photos:
    photo = Path(r'C:\Users\xucla\Documents\CAMILA\uninter') / name
    uri = 'data:image/jpeg;base64,' + base64.b64encode(photo.read_bytes()).decode('ascii')
    figs.append(f'<figure><img src="{uri}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
previous = (root / 'Encontro_II_Camila_previa.html').read_text(encoding='utf-8')
html = previous.split('<p class="relato">', 1)[0].replace('Encontro II |', 'Encontro III |').replace('15/08/2026', '22/08/2026')
html += '<p class="relato">' + escape(report) + '</p><h2>3. REGISTROS FOTOGRÁFICOS</h2>' + ''.join(figs)
html += '<h1>PLANO DE AULA</h1>' + plan_html
html += '<footer><strong>Comentário para a postagem</strong><p>Prezado(a) professor(a), encaminho o relatório, os registros fotográficos e o plano de aula do Encontro III, realizado em 22/08/2026, pela manhã, no polo Uninter Centro Lapad, Salvador/BA. O trabalho apresenta o jogo Encontre as Imagens e uma proposta de contagem e registro de quantidades para o 1º ano do Ensino Fundamental. Atenciosamente, Camila Santiago.</p></footer></main></html>'
output = root / 'Encontro_III_Camila_previa.html'
output.write_text(html, encoding='utf-8')
assert html.count('<figure>') == 3
assert 'Jogo da Borboleta' not in html
assert '15/08/2026' not in html
print(output)
