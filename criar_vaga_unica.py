import requests
import json
import time

url = "http://127.0.0.1:8001/intake/text"

# Usar timestamp para garantir unicidade
timestamp = int(time.time())

payload = {
    "raw_text": f"""Engenheiro de Dados na DataCorp Solutions
Localização: Rio de Janeiro - Híbrido
Modalidade: Híbrido
Salário: R$ 14.000 - 18.000

Vaga para Engenheiro de Dados com experiência em Python, Spark e AWS.
ID Único: {timestamp}

Responsabilidades:
- Construir pipelines de dados escaláveis
- Otimizar consultas SQL em BigQuery
- Implementar soluções em AWS (Glue, EMR, S3)

Requisitos:
- 5+ anos com Python
- Experiência com Spark e SQL
- Conhecimento em AWS
- Inglês fluente

Benefícios:
- Vale alimentação
- Plano de saúde premium
- Bônus por performance""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando vaga única com auto_analyze=False...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", json.dumps(response.json(), indent=2, ensure_ascii=False))