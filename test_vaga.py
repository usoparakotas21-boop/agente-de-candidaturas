import requests
import json

url = "http://127.0.0.1:8002/intake/text"

payload = {
    "raw_text": """Desenvolvedor Full Stack Pleno - Empresa Inovação Tech
Localização: São Paulo - Híbrido
Modalidade: Híbrido
Salário: R$ 10.000 - 14.000
URL: https://gupy.io/vaga/12345

Descrição: Buscamos um desenvolvedor full stack com experiência em Python e React.

Responsabilidades:
- Desenvolver aplicações web com React e FastAPI
- Integrar com APIs externas

Requisitos:
- 3+ anos com Python
- Conhecimento em React
- SQL e Docker""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando vaga...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", json.dumps(response.json(), indent=2, ensure_ascii=False))