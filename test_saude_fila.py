"""
Testar vaga com saúde na fila
"""
import requests
import json

url = "http://127.0.0.1:8001/intake/text"

# Vaga com auto_analyze=False para ir para a fila
payload = {
    "raw_text": """Desenvolvedor Python na Tech Startups Brasil
Localização: São Paulo - Remoto
Modalidade: Remoto

Vaga para desenvolvedor Python com experiência em FastAPI e SQLAlchemy.
Trabalho remoto com horário flexível. Requisitos: 3+ anos de experiência.""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("=" * 60)
print("TESTE: Vaga com auto_analyze=False")
print("=" * 60)

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
result = response.json()
print(f"Resposta: {json.dumps(result, indent=2, ensure_ascii=False)}")

# Verificar a fila
print("\n" + "=" * 60)
print("VERIFICANDO FILA")
print("=" * 60)

queue_response = requests.get("http://127.0.0.1:8001/queue/?limit=5")
queue_data = queue_response.json()
print(f"Itens na fila: {len(queue_data.get('items', []))}")

for item in queue_data.get('items', []):
    print(f"\nID: {item.get('id')}")
    print(f"Título: {item.get('title')}")
    print(f"Empresa: {item.get('company')}")
    print(f"Decisão: {item.get('decision')}")
    print(f"Status: {item.get('status')}")
    print(f"Saúde: {item.get('health_score')} - {item.get('health_band')}")
    print(f"Fraude suspeita: {item.get('fraud_suspected')}")