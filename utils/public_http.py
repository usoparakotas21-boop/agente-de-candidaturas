"""Public-only HTTP transports shared by synchronous intake and async scrapers."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class SourceFetchError(RuntimeError):
    pass


def _public_addresses(url: str) -> list[str]:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise SourceFetchError("Link publico invalido.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceFetchError("Link publico invalido.")
    if parsed.username or parsed.password:
        raise SourceFetchError("Link com credenciais nao permitido.")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = socket.getaddrinfo(parsed.hostname, port or default_port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SourceFetchError("Nao foi possivel localizar o site da vaga.") from exc
    if not addresses:
        raise SourceFetchError("Nao foi possivel localizar o site da vaga.")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise SourceFetchError("O link nao aponta para um site publico.")
    return list(dict.fromkeys(address[4][0] for address in addresses))


def _validate_public_url(url: str) -> str:
    _public_addresses(url)
    return url


class _PublicURLTransport(httpx.HTTPTransport):
    """Connect to a validated literal IP while retaining Host and TLS identity.

    Resolution and connection share the same address, closing DNS rebinding.
    HTTPX/httpcore forward sni_hostname to TLS certificate verification too.
    Each redirect is resolved independently; environment proxies are disabled.
    """

    def __init__(self):
        # Different names may share an IP; never reuse TLS across identities.
        super().__init__(limits=httpx.Limits(max_keepalive_connections=0), trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        addresses = _public_addresses(str(request.url))
        target = request.url.copy_with(host=addresses[0])
        headers = request.headers.copy()
        headers["Host"] = request.url.netloc.decode("ascii")
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = request.url.host
        pinned = httpx.Request(
            request.method, target, headers=headers, stream=request.stream,
            extensions=extensions,
        )
        return super().handle_request(pinned)


class PublicAsyncTransport(httpx.AsyncHTTPTransport):
    def __init__(self, proxy=None):
        super().__init__(limits=httpx.Limits(max_keepalive_connections=0), trust_env=False, proxy=proxy)

    async def handle_async_request(self, request):
        addresses = await asyncio.to_thread(_public_addresses, str(request.url))
        target = request.url.copy_with(host=addresses[0])
        headers = request.headers.copy()
        headers["Host"] = request.url.netloc.decode("ascii")
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = request.url.host
        pinned = httpx.Request(request.method, target, headers=headers,
                               stream=request.stream, extensions=extensions)
        return await super().handle_async_request(pinned)
