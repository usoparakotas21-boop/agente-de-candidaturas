import requests
import json

url = "http://127.0.0.1:8001/intake/text"

payload = {
    "raw_text": """Desenvolvedor Full Stack na Tech Startups Brasil
Localização: São Paulo - Remoto
Modalidade: Remoto
Salário: R$ 8.000 - 10.000

Vaga para desenvolvedor full stack com Python e React.
Experiência em FastAPI e SQLAlchemy.
Trabalho remoto com horário flexível.

Responsabilidades:
- Desenvolver APIs RESTful com FastAPI
- Criar interfaces com React
- Gerenciar banco de dados PostgreSQL
- Participar de reuniões de planejamento

Requisitos:
- 3+ anos de experiência com Python
- Conhecimento em React
- Experiência com banco de dados
- Inglês intermediário

Benefícios:
- Vale refeição
- Plano de saúde
- Horário flexível""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", response.text)