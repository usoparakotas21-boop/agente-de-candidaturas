import socket
from unittest.mock import patch

import httpx
import pytest
from httpcore._backends.mock import AsyncMockBackend, AsyncMockStream

from utils.anti_ban import AntiBanPolicy
from utils.http_client import SafeHttpClient, criar_cliente_protegido
from utils.public_http import PublicAsyncTransport, SourceFetchError


def addresses(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.asyncio
async def test_async_client_redirect_cannot_reach_internal_ip():
    client = criar_cliente_protegido(policy=AntiBanPolicy(min_delay_seconds=0, max_delay_seconds=0))
    backend = AsyncMockBackend([b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/secret\r\nContent-Length: 0\r\n\r\n'])
    assert isinstance(client._transport, PublicAsyncTransport)
    client._transport._pool._network_backend = backend
    calls = []
    connect = backend.connect_tcp
    async def tracked(**kwargs):
        calls.append(kwargs['host'])
        return await connect(**kwargs)
    def resolve(host, *args, **kw):
        return addresses('127.0.0.1' if host == '127.0.0.1' else '8.8.8.8')
    backend.connect_tcp = tracked
    with patch('socket.getaddrinfo', side_effect=resolve):
        async with client:
            with pytest.raises(SourceFetchError):
                await client.get('https://jobs.example')
    assert calls == ['8.8.8.8']


@pytest.mark.asyncio
async def test_scraper_transport_pins_ip_and_verifies_original_tls_name():
    transport = PublicAsyncTransport()
    backend = AsyncMockBackend([b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'])
    transport._pool._network_backend = backend
    calls, names = [], []
    connect = backend.connect_tcp
    async def tracked(**kwargs):
        calls.append(kwargs['host'])
        return await connect(**kwargs)
    async def tls(self, **kwargs):
        names.append(kwargs['server_hostname'])
        return self
    backend.connect_tcp = tracked
    with patch('socket.getaddrinfo', side_effect=[addresses('8.8.8.8'), addresses('127.0.0.1')]) as dns, \
         patch.object(AsyncMockStream, 'start_tls', tls):
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            http = SafeHttpClient(client=client, policy=AntiBanPolicy(min_delay_seconds=0, max_delay_seconds=0))
            assert await http.get_json('https://jobs.example/path') == {}
    assert calls == ['8.8.8.8'] and names == ['jobs.example'] and dns.call_count == 1


@pytest.mark.asyncio
async def test_env_proxies_are_disabled_for_public_sources(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:8888')
    monkeypatch.setenv('ALL_PROXY', 'http://127.0.0.1:8888')
    async with criar_cliente_protegido() as client:
        assert not client._trust_env
        assert not client._mounts
