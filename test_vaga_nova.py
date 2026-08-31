import requests
import json

url = "http://127.0.0.1:8002/intake/text"

payload = {
    "raw_text": """Desenvolvedor Backend - Tech Solutions
Localização: Remoto
Modalidade: Remoto
Descrição: Vaga para desenvolvedor backend com Python e FastAPI.""",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando vaga...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", json.dumps(response.json(), indent=2, ensure_ascii=False))