"""Send the same signed Mercado Pago notification twice for an idempotency check.

This is intentionally opt-in: it never creates a payment and it requires an
existing payment id from a controlled checkout. The webhook secret is read
from the environment and is never printed or accepted as a command argument.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from typing import Any

import requests


def _signature(secret: str, payment_id: str, request_id: str, timestamp: int) -> str:
    manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
    digest = hmac.new(
        secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"ts={timestamp},v1={digest}"


def _payload(path: str | None, payment_id: str) -> dict[str, Any]:
    if path:
        candidate = json.loads(open(path, encoding="utf-8").read())
        if not isinstance(candidate, dict):
            raise ValueError("O payload precisa ser um objeto JSON.")
        candidate.setdefault("type", "payment")
        candidate.setdefault("data", {}).setdefault("id", payment_id)
        return candidate
    return {"type": "payment", "data": {"id": payment_id}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("MERCADOPAGO_WEBHOOK_URL", ""),
        help="URL pública do webhook (também pode vir de MERCADOPAGO_WEBHOOK_URL).",
    )
    parser.add_argument(
        "--payment-id",
        default=os.getenv("MERCADOPAGO_PAYMENT_ID", ""),
        help="ID do pagamento aprovado no checkout controlado.",
    )
    parser.add_argument(
        "--payload-file",
        default="",
        help="Opcional: JSON original da notificação para repetir exatamente o payload.",
    )
    parser.add_argument(
        "--request-id",
        default="",
        help="Opcional: request id fixo para repetir a mesma entrega.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o formato da entrega sem fazer requisições.",
    )
    args = parser.parse_args()

    url = args.url.strip()
    secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    payment_id = args.payment_id.strip()
    request_id = args.request_id.strip() or f"codex-replay-{uuid.uuid4().hex}"
    if not url or not secret or not payment_id:
        print(
            "Defina MERCADOPAGO_WEBHOOK_URL, MERCADOPAGO_WEBHOOK_SECRET e "
            "MERCADOPAGO_PAYMENT_ID (ou informe os argumentos equivalentes).",
            file=sys.stderr,
        )
        return 2

    payload = _payload(args.payload_file.strip() or None, payment_id)
    timestamp = int(time.time())
    headers = {
        "content-type": "application/json",
        "x-request-id": request_id,
        "x-signature": _signature(secret, payment_id, request_id, timestamp),
    }
    if args.dry_run:
        print(json.dumps({"url": url, "payload": payload, "request_id": request_id}, indent=2))
        return 0

    results: list[tuple[int, dict[str, Any] | None]] = []
    for attempt in (1, 2):
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        try:
            body = response.json()
        except ValueError:
            body = None

        results.append((response.status_code, body if isinstance(body, dict) else None))
        summary = {
            "attempt": attempt,
            "http_status": response.status_code,
            "received": body.get("received") if isinstance(body, dict) else None,
            "verified": body.get("verified") if isinstance(body, dict) else None,
            "idempotent": body.get("idempotent") if isinstance(body, dict) else None,
            "payment_status": body.get("status") if isinstance(body, dict) else None,
            "receipt": body.get("receipt") if isinstance(body, dict) else None,
        }
        print(json.dumps(summary, ensure_ascii=False))

    successful_delivery = all(
        200 <= status < 300 and body is not None and body.get("verified") is True
        for status, body in results
    )
    duplicate_was_idempotent = bool(results[1][1] and results[1][1].get("idempotent") is True)
    if not successful_delivery or not duplicate_was_idempotent:
        print(
            "Falha na validação: confira configuração, assinatura e idempotência; "
            "nenhum corpo integral da resposta foi exibido.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
