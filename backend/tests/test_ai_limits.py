import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from pydantic import SecretStr

from backend.config import Settings
from backend.gemini import AIError, GeminiService
from backend.schemas import ChatRequest


class ProviderAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_blocked_attempt_never_contacts_the_provider(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={})

        quota = Mock(side_effect=AIError(429, "AI request allowance reached."))
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            service = GeminiService(
                Settings(gemini_api_key=SecretStr("test-key-not-real")),
                client, before_request=quota,
            )
            with self.assertRaises(AIError) as error:
                await service.chat(ChatRequest(message="Hello"), [])
        self.assertEqual(error.exception.status_code, 429)
        quota.assert_called_once_with()
        self.assertEqual(requests, [])

    async def test_missing_configuration_does_not_consume_an_allowance(self):
        quota = Mock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
            service = GeminiService(
                Settings(gemini_api_key=SecretStr(" ")), client, before_request=quota,
            )
            with self.assertRaises(AIError) as error:
                await service.chat(ChatRequest(message="Hello"), [])
        self.assertEqual(error.exception.status_code, 503)
        quota.assert_not_called()

    async def test_each_real_attempt_including_retry_is_counted(self):
        for unavailable_attempts in (1, 2):
            with self.subTest(unavailable_attempts=unavailable_attempts):
                requests = []

                def respond(request):
                    requests.append(request)
                    if len(requests) <= unavailable_attempts:
                        return httpx.Response(503)
                    return httpx.Response(200, json={
                        "candidates": [{"content": {"parts": [{"text": "Hello."}]}, "finishReason": "STOP"}],
                    })

                quota = Mock()
                with patch("backend.gemini.asyncio.sleep", new_callable=AsyncMock):
                    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                        service = GeminiService(
                            Settings(gemini_api_key=SecretStr("test-key-not-real")), client, before_request=quota,
                        )
                        self.assertEqual(await service.chat(ChatRequest(message="Hello"), []), "Hello.")
                self.assertEqual(len(requests), unavailable_attempts + 1)
                self.assertEqual(quota.call_count, unavailable_attempts + 1)

    async def test_a_retry_cannot_exceed_the_allowance(self):
        for allowed_attempts in (1, 2):
            with self.subTest(allowed_attempts=allowed_attempts):
                requests = []

                def respond(request):
                    requests.append(request)
                    return httpx.Response(503)

                quota = Mock(side_effect=[None] * allowed_attempts + [AIError(429, "AI request allowance reached.")])
                with patch("backend.gemini.asyncio.sleep", new_callable=AsyncMock):
                    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                        service = GeminiService(
                            Settings(gemini_api_key=SecretStr("test-key-not-real")), client, before_request=quota,
                        )
                        with self.assertRaises(AIError) as error:
                            await service.chat(ChatRequest(message="Hello"), [])
                self.assertEqual(error.exception.status_code, 429)
                self.assertEqual(len(requests), allowed_attempts)
                self.assertEqual(quota.call_count, allowed_attempts + 1)


if __name__ == "__main__":
    unittest.main()
