"""Offline tests exercise the real HTTPX -> httpcore connection path."""
import socket
from unittest.mock import patch

import httpx
import pytest
from httpcore._backends.mock import MockBackend, MockStream

from app.job_source_fetcher import (
    SourceFetchError, _PublicURLTransport, _validate_public_url, fetch_job_posting,
)


def address(ip):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET,
             socket.SOCK_STREAM, 6, '', (ip, 443))]


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_destinations_rejected(ip):
    with patch('socket.getaddrinfo', return_value=address(ip)):
        with pytest.raises(SourceFetchError):
            _validate_public_url('https://jobs.example/path')


@pytest.mark.parametrize('url', ['https://jobs.example:bad', 'https://jobs.example:99999',
                                 'https://[invalid', 'file:///etc/passwd', 'https://u:p@jobs.example'])
def test_malformed_urls_are_controlled_errors(url):
    with pytest.raises(SourceFetchError):
        _validate_public_url(url)


def test_empty_or_mixed_dns_answers_fail_closed():
    for answers in ([], address('8.8.8.8') + address('127.0.0.1')):
        with patch('socket.getaddrinfo', return_value=answers), pytest.raises(SourceFetchError):
            _validate_public_url('https://jobs.example')


def test_rebinding_pins_connection_and_preserves_tls_identity():
    transport = _PublicURLTransport()
    backend = MockBackend([b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'])
    transport._pool._network_backend = backend
    # DNS would change to loopback if the transport resolved a second time.
    with patch('socket.getaddrinfo', side_effect=[address('8.8.8.8'), address('127.0.0.1')]) as dns, \
         patch.object(backend, 'connect_tcp', wraps=backend.connect_tcp) as connect, \
         patch.object(MockStream, 'start_tls', autospec=True, side_effect=lambda self, **kw: self) as tls, \
         patch.object(MockStream, 'write', autospec=True) as write, \
         httpx.Client(transport=transport, trust_env=False) as client:
        response = client.get('https://jobs.example:8443/path?q=1')
        assert response.status_code == 200
        assert dns.call_count == 1
        assert connect.call_args.kwargs['host'] == '8.8.8.8'
        assert connect.call_args.kwargs['port'] == 8443
        assert tls.call_args.kwargs['server_hostname'] == 'jobs.example'
        assert b'Host: jobs.example:8443' in b''.join(c.args[1] for c in write.call_args_list)
        assert response.request.url.host == 'jobs.example'


def test_redirect_to_private_host_never_connects():
    transport = _PublicURLTransport()
    backend = MockBackend([b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/metadata\r\nContent-Length: 0\r\n\r\n'])
    transport._pool._network_backend = backend
    def resolve(host, *args, **kwargs):
        return address('127.0.0.1' if host == '127.0.0.1' else '8.8.8.8')
    with patch('app.job_source_fetcher._PublicURLTransport', return_value=transport), \
         patch('socket.getaddrinfo', side_effect=resolve), \
         patch.object(backend, 'connect_tcp', wraps=backend.connect_tcp) as connect:
        with pytest.raises(SourceFetchError):
            fetch_job_posting('https://jobs.example/path')
        assert connect.call_count == 1


def test_shared_ip_does_not_reuse_tls_between_hostnames():
    transport = _PublicURLTransport()
    backend = MockBackend([b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'])
    transport._pool._network_backend = backend
    with patch('socket.getaddrinfo', return_value=address('8.8.8.8')), \
         patch.object(backend, 'connect_tcp', wraps=backend.connect_tcp) as connect, \
         patch.object(MockStream, 'start_tls', autospec=True, side_effect=lambda self, **kw: self) as tls, \
         httpx.Client(transport=transport, trust_env=False) as client:
        client.get('https://one.example')
        client.get('https://two.example')
        assert connect.call_count == 2
        assert [c.kwargs['server_hostname'] for c in tls.call_args_list] == ['one.example', 'two.example']
