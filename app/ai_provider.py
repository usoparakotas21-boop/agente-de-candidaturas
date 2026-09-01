import json
import os

import httpx


class AIProviderError(RuntimeError):
    pass


async def evaluate_interview_answer(question: str, answer: str, context: str = "") -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIProviderError("GEMINI_API_KEY nao configurada")
    prompt = f"""Voce e um coach de entrevistas de emprego no Brasil.
Analise a resposta abaixo com honestidade e linguagem acolhedora.
Retorne SOMENTE JSON valido com as chaves: score (numero de 0 a 100), title (curto), strengths (lista de strings), improvements (lista de strings), rewritten (resposta melhorada em primeira pessoa) e next_tip (uma dica curta).
Nao invente fatos sobre o candidato. Considere clareza, contexto, acao, resultado, evidencias e relacao com a pergunta.

Pergunta: {question}
Contexto opcional da vaga: {context or 'nao informado'}
Resposta do candidato: {answer}"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"}}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(url, params={"key": api_key}, json=payload)
        if response.status_code >= 400:
            raise AIProviderError(f"Gemini respondeu HTTP {response.status_code}")
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(raw)
    except AIProviderError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIProviderError("Nao foi possivel obter uma analise da IA") from exc
    try:
        score = max(0, min(100, int(result.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {"score": score, "title": str(result.get("title") or "Analise da IA"), "strengths": [str(x) for x in result.get("strengths", [])][:4], "improvements": [str(x) for x in result.get("improvements", [])][:4], "rewritten": str(result.get("rewritten") or ""), "next_tip": str(result.get("next_tip") or ""), "provider": "gemini-2.5-flash"}
