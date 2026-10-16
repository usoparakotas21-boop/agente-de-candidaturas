from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security import SecurityHeadersMiddleware


def test_untrusted_origins_are_blocked_before_mutation():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    calls = []

    @app.post("/change")
    def change():
        calls.append(True)
        return {"ok": True}

    with patch("app.auth.APP_BASE_URL", "https://candidaturacerta.com.br"), TestClient(app) as client:
        for origin in ("https://evil.example", "https://evil.candidaturacerta.com.br", "null"):
            response = client.post("/change", headers={"Origin": origin})
            assert response.status_code == 403
            assert response.headers["x-content-type-options"] == "nosniff"
        assert not calls
        assert client.post("/change", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.post("/change", headers={"Origin": "https://candidaturacerta.com.br"}).status_code == 200
        # Origin-less API clients keep their existing authentication contract.
        assert client.post("/change").status_code == 200


def test_webhooks_and_bearer_extension_keep_their_own_authentication():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.post("/webhooks/mercadopago")
    @app.post("/api/billing/webhook")
    @app.post("/api/copilot/profile")
    def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/webhooks/mercadopago", headers={"Origin": "https://provider.example"}).status_code == 200
        assert client.post("/api/billing/webhook", headers={"Origin": "https://provider.example"}).status_code == 200
        assert client.post("/api/copilot/profile", headers={"Origin": "chrome-extension://example", "Authorization": "Bearer test"}).status_code == 200
        assert client.post("/api/copilot/profile", headers={"Origin": "https://evil.example"}).status_code == 403
