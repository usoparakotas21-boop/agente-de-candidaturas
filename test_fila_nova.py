"""
Criar uma vaga NOVA com auto_analyze=False para ir para a fila
"""
import requests
import json
import time

url = "http://127.0.0.1:8001/intake/text"

# Usar timestamp para garantir que é uma vaga nova
timestamp = int(time.time())

payload = {
    "raw_text": f"""Desenvolvedor Python Sênior na Tech Innovations
Localização: São Paulo - Remoto
Modalidade: Remoto
Salário: R$ 12.000 - 15.000

Vaga para desenvolvedor Python sênior com experiência em FastAPI, SQLAlchemy e AWS.
Responsabilidades:
- Desenvolver APIs RESTful
- Gerenciar banco de dados PostgreSQL
- Deploy em ambiente AWS
- Liderar equipe de desenvolvimento

Requisitos:
- 5+ anos de experiência com Python
- Experiência com FastAPI e SQLAlchemy
- Conhecimento em AWS (EC2, RDS, S3)
- Inglês avançado

Benefícios:
- Vale refeição
- Plano de saúde
- Bônus anual
- Horário flexível

Vaga ID: {timestamp}
""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("=" * 60)
print("CRIANDO VAGA NOVA com auto_analyze=False")
print("=" * 60)

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
result = response.json()
print(f"Resposta: {json.dumps(result, indent=2, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("VERIFICANDO FILA")
print("=" * 60)

# Aguardar um momento para a vaga ser processada
time.sleep(1)

queue_response = requests.get("http://127.0.0.1:8001/queue/?limit=10")
queue_data = queue_response.json()
items = queue_data.get('items', [])
print(f"Itens na fila: {len(items)}")

if items:
    for item in items:
        print(f"\n📋 ID: {item.get('id')}")
        print(f"   Título: {item.get('title')}")
        print(f"   Empresa: {item.get('company')}")
        print(f"   Decisão: {item.get('decision')}")
        print(f"   Status: {item.get('status')}")
        print(f"   🏥 Saúde: {item.get('health_score')} - {item.get('health_band')}")
        print(f"   🚨 Fraude suspeita: {item.get('fraud_suspected')}")
        
        health_signals = item.get('health_signals', [])
        if health_signals:
            print("   📌 Sinais:")
            for signal in health_signals[:5]:
                print(f"      - {signal.get('label')} ({signal.get('adjustment')})")
else:
    print("   Nenhum item na fila.")