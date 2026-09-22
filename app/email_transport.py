"""Shared transactional email transport with Brevo HTTPS and SMTP support."""

from __future__ import annotations

import base64
import os
import smtplib
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Callable, Iterator

import httpx

BREVO_EMAIL_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
DEFAULT_SENDER = "contato@candidaturacerta.com.br"


def brevo_api_key() -> str:
    """Return the optional Brevo key without logging or exposing it."""
    return os.getenv("BREVO_API_KEY", "").strip()


def select_email_transport(smtp_config: dict[str, object] | None) -> dict[str, object] | None:
    """Prefer Brevo HTTPS when opted in, otherwise use the configured SMTP relay."""
    if not brevo_api_key():
        return smtp_config
    sender = str((smtp_config or {}).get("sender") or os.getenv("SMTP_FROM_EMAIL", "")).strip()
    return {"transport": "brevo_api", "sender": sender or DEFAULT_SENDER}


def send_via_brevo_api(
    message: EmailMessage,
    *,
    timeout: float,
    http_client_factory: Callable = httpx.Client,
) -> None:
    """Send a plain-text EmailMessage and attachments using Brevo's HTTPS API."""
    api_key = brevo_api_key()
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is not configured")

    sender = str(message.get("From") or "").strip()
    sender_parts = getaddresses([sender])
    recipients = [
        {"email": address, **({"name": name} if name else {})}
        for name, address in getaddresses(message.get_all("To", []))
        if address
    ]
    if not sender_parts or not sender_parts[0][1] or not recipients:
        raise ValueError("Brevo message has no sender or recipient")

    sender_name, sender_address = sender_parts[0]
    payload: dict[str, object] = {
        "sender": {"email": sender_address, **({"name": sender_name} if sender_name else {})},
        "to": recipients,
        "subject": str(message.get("Subject") or ""),
    }
    reply_to = str(message.get("Reply-To") or "").strip()
    if reply_to:
        reply_parts = getaddresses([reply_to])
        if reply_parts and reply_parts[0][1]:
            reply_name, reply_address = reply_parts[0]
            payload["replyTo"] = {
                "email": reply_address,
                **({"name": reply_name} if reply_name else {}),
            }

    body_part = message.get_body(preferencelist=("plain",))
    payload["textContent"] = body_part.get_content() if body_part is not None else ""
    attachments: list[dict[str, str]] = []
    for part in message.iter_attachments():
        content = part.get_payload(decode=True)
        if content is None:
            continue
        attachments.append({
            "name": part.get_filename() or "attachment",
            "content": base64.b64encode(content).decode("ascii"),
        })
    if attachments:
        payload["attachment"] = attachments

    with http_client_factory(timeout=timeout) as client:
        response = client.post(
            BREVO_EMAIL_ENDPOINT,
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()


@contextmanager
def smtp_client(
    config: dict[str, object],
    *,
    timeout: float,
    smtp_factory: Callable = smtplib.SMTP,
    smtp_ssl_factory: Callable = smtplib.SMTP_SSL,
) -> Iterator[object]:
    """Open SMTP with STARTTLS or implicit TLS, including the common port 465 setup."""
    host = str(config["host"])
    port = int(config["port"])
    if bool(config.get("use_ssl")):
        with smtp_ssl_factory(host, port, timeout=timeout) as client:
            yield client
        return
    with smtp_factory(host, port, timeout=timeout) as client:
        if bool(config.get("use_tls")):
            client.starttls()
        yield client


def send_email_message(
    message: EmailMessage,
    config: dict[str, object],
    *,
    timeout: float = 10,
    smtp_factory: Callable = smtplib.SMTP,
    smtp_ssl_factory: Callable = smtplib.SMTP_SSL,
    http_client_factory: Callable = httpx.Client,
) -> str:
    """Deliver one message through the selected provider and return its transport."""
    if config.get("transport") == "brevo_api":
        send_via_brevo_api(message, timeout=timeout, http_client_factory=http_client_factory)
        return "brevo_api"

    with smtp_client(
        config,
        timeout=timeout,
        smtp_factory=smtp_factory,
        smtp_ssl_factory=smtp_ssl_factory,
    ) as client:
        username = str(config.get("username") or "")
        if username:
            client.login(username, str(config.get("password") or ""))
        client.send_message(message)
    return "smtp"
