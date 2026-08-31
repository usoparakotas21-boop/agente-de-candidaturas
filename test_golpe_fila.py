"""
Script para testar vaga golpe na fila
"""
import requests
import json

url = "http://127.0.0.1:8001/intake/text"

payload = {
    "raw_text": "Ganhe R$ 10.000 por dia! Empresa Confidencial. Taxa de cadastro R$ 50. Marketing de rede. Seja seu próprio chefe. Envie seu CPF e foto do RG.",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("=" * 60)
print("TESTE: Vaga Golpe com auto_analyze=False")
print("=" * 60)

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Resposta: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")