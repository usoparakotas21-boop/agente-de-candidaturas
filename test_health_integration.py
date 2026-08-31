"""
Teste de integração do módulo de saúde da vaga com job_quality
"""

from app.job_quality import assess_job_capture

print("=" * 60)
print("TESTE 1: Vaga Normal")
print("=" * 60)

vaga_normal = {
    'title': 'Desenvolvedor Full Stack',
    'company': 'Tech Startups Brasil',
    'description': 'Vaga para desenvolvedor full stack com Python e React. Experiência em FastAPI e SQLAlchemy. Trabalho remoto com horário flexível. Requisitos: 3+ anos de experiência, conhecimento em banco de dados.',
    'url': 'https://gupy.io/vaga/123',
    'salary': 'R$ 8.000 - 10.000',
}

resultado = assess_job_capture(vaga_normal)
print(f'Decisão: {resultado["decision"]}')
print(f'Confiança: {resultado["confidence"]}%')
print(f'Saúde: {resultado["health"]["band"]} ({resultado["health"]["score"]})')
print(f'Fraude suspeita: {resultado["health"]["fraud_suspected"]}')
print(f'Motivos: {resultado["reasons"]}')
print()

print("=" * 60)
print("TESTE 2: Vaga Golpe")
print("=" * 60)

vaga_golpe = {
    'title': 'Ganhe R$ 10.000 por dia!',
    'company': 'Empresa Confidencial',
    'description': 'Taxa de cadastro R$ 50. Marketing de rede. Seja seu próprio chefe. Envie seu CPF e foto do RG.',
    'url': 'bit.ly/vaga',
    'salary': '',
}

resultado = assess_job_capture(vaga_golpe)
print(f'Decisão: {resultado["decision"]}')
print(f'Saúde: {resultado["health"]["band"]} ({resultado["health"]["score"]})')
print(f'Fraude suspeita: {resultado["health"]["fraud_suspected"]}')
print(f'Motivos: {resultado["reasons"]}')
print()
print("Sinais de saúde:")
for sinal in resultado["health"]["signals"]:
    print(f'  - {sinal["label"]} ({sinal["adjustment"]})')
    if sinal.get("evidence"):
        print(f'    Evidência: {sinal["evidence"]}')