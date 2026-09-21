import json as json_lib
import unittest
from unittest.mock import patch

import httpx

from app import ai_provider


class _FakeGeminiClient:
    raw_result = {"score": 80, "title": "Boa resposta", "strengths": ["Clareza"], "improvements": ["Detalhar o resultado"], "rewritten": "Uma resposta melhor", "next_tip": "Use um exemplo concreto."}
    raw_body = None
    last_url = None

    def __init__(self, *, timeout):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, *, params, json):
        type(self).last_url = url
        if self.raw_body is not None:
            return httpx.Response(200, content=self.raw_body)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json_lib.dumps(self.raw_result)}]}}]},
        )


class AiProviderResponseContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_result = _FakeGeminiClient.raw_result
        self._original_body = _FakeGeminiClient.raw_body

    async def asyncTearDown(self):
        _FakeGeminiClient.raw_result = self._original_result
        _FakeGeminiClient.raw_body = self._original_body

    async def _evaluate(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            ai_provider.httpx, "AsyncClient", _FakeGeminiClient
        ):
            return await ai_provider.evaluate_interview_answer("Pergunta válida", "Resposta com conteúdo suficiente")

    async def test_valid_result_is_normalized_and_bounded(self):
        _FakeGeminiClient.raw_result = {
            "score": 82.9,
            "title": "  Título  ",
            "strengths": [" A " * 250, "", 123, "B", "C", "D", "E"],
            "improvements": "texto que deveria ser uma lista",
            "rewritten": "R" * 5000,
            "next_tip": "D" * 800,
        }

        result = await self._evaluate()

        self.assertEqual(result["score"], 82)
        self.assertEqual(result["title"], "Título")
        self.assertEqual(len(result["strengths"]), 4)
        self.assertTrue(all(len(item) <= 300 for item in result["strengths"]))
        self.assertEqual(result["improvements"], [])
        self.assertEqual(len(result["rewritten"]), 4000)
        self.assertEqual(len(result["next_tip"]), 500)
        self.assertEqual(result["provider"], "gemini-3.6-flash")
        self.assertIn("/models/gemini-3.6-flash:generateContent", _FakeGeminiClient.last_url)

    async def test_non_object_result_is_controlled_provider_error(self):
        _FakeGeminiClient.raw_result = ["unexpected", "array"]

        with self.assertRaisesRegex(ai_provider.AIProviderError, "formato invalido"):
            await self._evaluate()

    async def test_non_numeric_boolean_and_non_finite_scores_are_rejected(self):
        for invalid_score in ("80", True, float("nan"), float("inf")):
            with self.subTest(score=invalid_score):
                _FakeGeminiClient.raw_result = {"score": invalid_score}
                with self.assertRaisesRegex(ai_provider.AIProviderError, "formato invalido"):
                    await self._evaluate()

    async def test_numeric_score_is_clamped_to_contract(self):
        _FakeGeminiClient.raw_result = {"score": 10**1000}

        result = await self._evaluate()

        self.assertEqual(result["score"], 100)

    async def test_oversized_provider_response_is_rejected_before_json_parsing(self):
        _FakeGeminiClient.raw_body = b"x" * (ai_provider.MAX_PROVIDER_RESPONSE_BYTES + 1)

        with self.assertRaisesRegex(ai_provider.AIProviderError, "maior que o limite"):
            await self._evaluate()


if __name__ == "__main__":
    unittest.main()
