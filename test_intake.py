"""
Script para testar o endpoint /intake/text via Python
"""
import requests
import json

# Vaga normal
url = "http://127.0.0.1:8001/intake/text"
payload = {
    "raw_text": "Desenvolvedor Python na Tech Startups Brasil\nLocalização: São Paulo - Remoto\nModalidade: Remoto\n\nVaga para desenvolvedor Python com experiência em FastAPI e SQLAlchemy. Trabalho remoto com horário flexível. Requisitos: 3+ anos de experiência.",
    "source": "texto",
    "auto_analyze": True,
    "reprocess_existing": False
}

print("=" * 60)
print("TESTE 1: Vaga Normal")
print("=" * 60)

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Resposta: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
print()

# Vaga golpe
payload_golpe = {
    "raw_text": "Ganhe R$ 10.000 por dia! Empresa Confidencial. Taxa de cadastro R$ 50. Marketing de rede. Seja seu próprio chefe. Envie seu CPF e foto do RG.",
    "source": "texto",
    "auto_analyze": True,
    "reprocess_existing": False
}

print("=" * 60)
print("TESTE 2: Vaga Golpe")
print("=" * 60)

response = requests.post(url, json=payload_golpe)
print(f"Status: {response.status_code}")
print(f"Resposta: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")