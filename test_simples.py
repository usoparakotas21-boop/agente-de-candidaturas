import requests
import json

url = "http://127.0.0.1:8001/intake/text"

payload = {
    "raw_text": "Desenvolvedor Python na Tech Startup",
    "source": "texto",
    "auto_analyze": False,
    "reprocess_existing": False
}

print("Enviando...")
response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Resposta:", response.text)