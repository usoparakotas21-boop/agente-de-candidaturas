import requests
import json

url = "http://127.0.0.1:8001/intake/text"

payload = {
    "raw_text": """Desenvolvedor Python Sênior na Tech Innovations
Localização: São Paulo - Remoto
Modalidade: Remoto
Salário: R$ 12.000 - 15.000

Vaga para desenvolvedor Python sênior com experiência em FastAPI, SQLAlchemy e AWS.

Responsabilidades:
- Desenvolver APIs RESTful
- Gerenciar banco de dados PostgreSQL
- Deploy em ambiente AWS

Requisitos:
- 5+ anos de experiência com Python
- Experiência com FastAPI e SQLAlchemy
- Conhecimento em AWS
- Inglês avançado

Benefícios:
- Vale refeição
- Plano de saúde
- Bônus anual""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando vaga com auto_analyze=False...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", json.dumps(response.json(), indent=2, ensure_ascii=False))