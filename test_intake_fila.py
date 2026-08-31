"""
Script para testar o endpoint /intake/text com auto_analyze=False
"""
import requests
import json

url = "http://127.0.0.1:8001/intake/text"

# Vaga normal com auto_analyze=False
payload = {
    "raw_text": "Desenvolvedor Python na Tech Startups Brasil\nLocalização: São Paulo - Remoto\nModalidade: Remoto\n\nVaga para desenvolvedor Python com experiência em FastAPI e SQLAlchemy. Trabalho remoto com horário flexível. Requisitos: 3+ anos de experiência.",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("=" * 60)
print("TESTE: Vaga com auto_analyze=False (deve ir para a fila)")
print("=" * 60)

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Resposta: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")