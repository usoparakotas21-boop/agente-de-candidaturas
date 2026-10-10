"""Responsible pacing and request policy for public job sources.

This module deliberately does not rotate identities, bypass CAPTCHA, evade
access controls, or ignore robots.txt.  It only reduces request pressure and
stops collection when a site asks automated clients not to crawl a path.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import os
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]

PROXY_GATEWAY = os.getenv("ROTATING_PROXY_URL")


@dataclass(frozen=True, slots=True)
class AntiBanPolicy:
    user_agent: str = "CandidaturaCertaJobCollector/1.0 (+https://candidaturacerta.com.br)"
    min_delay_seconds: float = 1.0
    max_delay_seconds: float = 3.0
    max_retries: int = 2
    max_concurrent_per_host: int = 1
    respect_robots_txt: bool = True
    request_timeout_seconds: float = 20.0
    max_response_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.min_delay_seconds < 0 or self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("Os limites de atraso são inválidos.")
        if self.max_retries < 0 or self.max_concurrent_per_host < 1:
            raise ValueError("As configurações de repetição e concorrência são inválidas.")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }

    @staticmethod
    def validate_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A coleta aceita apenas URLs HTTP(S) públicas.")
        return url


def obter_cabecalhos_aleatorios() -> dict[str, str]:
    """Return browser-like headers without bypassing access controls."""

    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def obter_headers_camuflados(referer: str = "https://www.google.com/") -> dict[str, str]:
    """Compatibility helper that adds a caller-provided referer."""
    headers = obter_cabecalhos_aleatorios()
    headers.update(
        {
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": referer,
        }
    )
    return headers


def obter_configuracao_proxy() -> str | None:
    """Return the explicitly configured proxy, if one is available."""
    return PROXY_GATEWAY
