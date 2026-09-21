import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, main, support_chat


class _FakeGeminiResponse:
    status_code = 200
    content = b"{}"

    def json(self):
        return {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({"topic": "plans"})}]}
            }]
        }


class _FakeGeminiClient:
    last_request = None

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        type(self).last_request = {"url": url, "headers": headers, "json": json}
        return _FakeGeminiResponse()


class _FakeGeminiEmptyCandidateResponse(_FakeGeminiResponse):
    def json(self):
        return {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}


class _FakeGeminiEmptyCandidateClient(_FakeGeminiClient):
    async def post(self, url, *, headers, json):
        return _FakeGeminiEmptyCandidateResponse()


class SupportChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_classifies_to_closed_topic_set_and_uses_server_key_header(self):
        _FakeGeminiClient.last_request = None
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}), patch.object(
            support_chat.httpx, "AsyncClient", _FakeGeminiClient
        ):
            topic = await support_chat.classify_support_topic("Qual o preço do Pro?")

        self.assertEqual(topic, "plans")
        self.assertEqual(set(support_chat.TOPIC_ANSWERS), set(support_chat.ALLOWED_TOPICS))
        request = _FakeGeminiClient.last_request
        self.assertIn("/models/gemini-3.6-flash:generateContent", request["url"])
        self.assertEqual(request["headers"]["x-goog-api-key"], "test-secret")
        self.assertNotIn("test-secret", request["url"])
        schema = request["json"]["generationConfig"]["responseSchema"]
        self.assertEqual(schema["properties"]["topic"]["enum"], list(support_chat.ALLOWED_TOPICS))
        generation_config = request["json"]["generationConfig"]
        self.assertEqual(generation_config["maxOutputTokens"], 128)
        self.assertEqual(generation_config["thinkingConfig"]["thinkingLevel"], "low")
        self.assertIn("untrusted_user_message", request["json"]["contents"][0]["parts"][0]["text"])

    async def test_empty_gemini_candidate_is_handled_as_provider_failure(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}), patch.object(
            support_chat.httpx, "AsyncClient", _FakeGeminiEmptyCandidateClient
        ):
            with self.assertRaisesRegex(RuntimeError, "não retornou uma classificação"):
                await support_chat.classify_support_topic("Qual o preço do Pro?")

    async def test_missing_gemini_key_is_reported_without_exposing_provider_details(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                await support_chat.classify_support_topic("Como funciona?")

    def test_local_fallback_classifies_common_questions_conservatively(self):
        self.assertEqual(support_chat.fallback_support_topic("Qual o limite de vagas por mês?"), "opportunity_limits")
        self.assertEqual(support_chat.fallback_support_topic("Como cancelar a assinatura do Pro?"), "subscription")
        self.assertEqual(support_chat.fallback_support_topic("Quero falar com o suporte"), "contact")
        self.assertEqual(support_chat.fallback_support_topic("Como funciona o site?"), "how_it_works")
        self.assertEqual(support_chat.fallback_support_topic("Quais são os planos e limites?"), "plans")
        self.assertEqual(support_chat.fallback_support_topic("Aceita Pix para pagar?"), "payment_methods")
        self.assertEqual(support_chat.fallback_support_topic("Como conecto meu Gmail?"), "email_alerts")
        self.assertEqual(support_chat.fallback_support_topic("Quero excluir minha conta"), "account_deletion")
        self.assertEqual(support_chat.fallback_support_topic("Meu currículo não chegou por e-mail"), "email_delivery")
        self.assertEqual(support_chat.fallback_support_topic("Quais formatos de currículo posso importar?"), "file_formats")
        self.assertEqual(support_chat.fallback_support_topic("Meu currículo é compatível com ATS?"), "ats_compatibility")
        self.assertEqual(support_chat.fallback_support_topic("Receberei alerta de vaga expirando?"), "expiring_alerts")
        self.assertEqual(support_chat.fallback_support_topic("Pergunta sem relação"), "unknown")

    def test_route_recovers_common_question_when_gemini_returns_unknown(self):
        app = FastAPI()
        app.include_router(support_chat.router)
        with (
            patch.object(support_chat, "_enforce_rate_limit"),
            patch.object(support_chat, "classify_support_topic", new=AsyncMock(return_value="unknown")),
            TestClient(app) as client,
        ):
            response = client.post("/api/support-chat", json={"message": "Como funciona o site?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("organiza as oportunidades", response.json()["answer"])
        self.assertIn("o envio não é automático", response.json()["answer"])

    def test_public_route_is_rate_limited_and_returns_only_curated_answer(self):
        app = FastAPI()
        app.include_router(support_chat.router)
        app.add_middleware(auth.AuthMiddleware)
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(support_chat, "_enforce_rate_limit") as limiter,
            patch.object(support_chat, "classify_support_topic", new=AsyncMock(return_value="plans")),
            TestClient(app) as client,
        ):
            response = client.post("/api/support-chat", json={"message": "Qual plano tem maior limite?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("R$ 99,00/mês", response.json()["answer"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        limiter.assert_called_once()
        self.assertIn("/api/support-chat", auth.AuthMiddleware.PUBLIC_PATHS)

    def test_public_route_falls_back_to_curated_answer_when_gemini_is_unavailable(self):
        app = FastAPI()
        app.include_router(support_chat.router)
        app.add_middleware(auth.AuthMiddleware)
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}),
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(support_chat, "_enforce_rate_limit"),
            patch.object(support_chat, "classify_support_topic", new=AsyncMock(side_effect=RuntimeError("Gemini indisponível"))),
            TestClient(app) as client,
        ):
            response = client.post("/api/support-chat", json={"message": "Qual o limite de vagas por mês?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("até 500", response.json()["answer"])

    def test_public_route_accepts_question_field_from_integration_example(self):
        app = FastAPI()
        app.include_router(support_chat.router)
        with (
            patch.object(support_chat, "_enforce_rate_limit"),
            patch.object(support_chat, "classify_support_topic", new=AsyncMock(return_value="contact")),
            TestClient(app) as client,
        ):
            response = client.post("/api/support-chat", json={"question": "Como falo com o suporte?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("(71) 99182-4951", response.json()["answer"])

    def test_landing_has_widget_and_video_embed_is_validated_and_optional(self):
        with patch.dict(os.environ, {}, clear=True):
            landing = main.root().body.decode("utf-8")
        self.assertIn("/static/support-chat.js?v=3", landing)
        self.assertIn('class="cc-support-safe-footer"', landing)
        self.assertNotIn("CANDIDATURA_CERTA_DEMO_VIDEO", landing)
        self.assertNotIn('id="demonstracao"', landing)

        with patch.dict(os.environ, {"DEMO_VIDEO_URL": "https://youtu.be/abcdefghijk"}):
            landing_with_video = main.root().body.decode("utf-8")
        self.assertIn("https://www.youtube-nocookie.com/embed/abcdefghijk", landing_with_video)

        with patch.dict(os.environ, {"DEMO_VIDEO_URL": "https://vimeo.com/123456789/unlistedHash"}):
            vimeo_landing = main.root().body.decode("utf-8")
        self.assertIn("https://player.vimeo.com/video/123456789?h=unlistedHash", vimeo_landing)

        with patch.dict(os.environ, {"DEMO_VIDEO_URL": "https://example.com/abcdefghijk"}):
            unsafe_video = main.root().body.decode("utf-8")
        self.assertNotIn('id="demonstracao"', unsafe_video)
        self.assertNotIn('src="https://example.com/abcdefghijk"', unsafe_video)

    def test_authenticated_shell_has_widget(self):
        dashboard = main._page(main.DASHBOARD_PATH).body.decode("utf-8")
        self.assertIn("/static/support-chat.js?v=3", dashboard)

    def test_widget_shows_accessible_common_question_shortcuts_without_html_injection(self):
        widget = (Path(__file__).resolve().parents[1] / "app" / "static" / "support-chat.js").read_text(encoding="utf-8")
        self.assertIn("Como funciona o site?", widget)
        self.assertIn("Como conecto Gmail ou Outlook?", widget)
        self.assertIn('aria-label", "Perguntas comuns"', widget)
        self.assertIn('faq.href = "/ajuda"', widget)
        self.assertIn("form.requestSubmit()", widget)
        self.assertIn("textContent", widget)
        self.assertNotIn("innerHTML", widget)

    def test_support_chat_reserves_space_below_public_footer(self):
        css = (Path(__file__).resolve().parents[1] / "app" / "static" / "support-chat.css").read_text(encoding="utf-8")
        widget = (Path(__file__).resolve().parents[1] / "app" / "static" / "support-chat.js").read_text(encoding="utf-8")
        self.assertIn(".cc-support-safe-footer{padding-bottom:calc(96px + env(safe-area-inset-bottom,0px))!important}", css)
        self.assertIn("/static/support-chat.css?v=3", widget)


if __name__ == "__main__":
    unittest.main()
