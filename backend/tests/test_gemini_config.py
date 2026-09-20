import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr

from backend import config
from backend.config import Settings
from backend.gemini import AIError, GeminiService
from backend.schemas import ChatRequest, TranslationRequest


def generated(text: str, finish: str = "STOP") -> dict[str, object]:
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}]}


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory(prefix=".config-test-", dir=Path(__file__).parent)
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root_env = root / ".env"
        self.backend_env = root / "backend.env"

    def load(self, *, gemini_api_key: SecretStr | None = None) -> Settings:
        with patch.dict(Settings.model_config, env_file=(self.root_env, self.backend_env)):
            return Settings() if gemini_api_key is None else Settings(gemini_api_key=gemini_api_key)

    def test_default_environment_paths_are_absolute_and_backend_is_last(self) -> None:
        backend = Path(config.__file__).resolve().parent
        self.assertEqual(Settings.model_config.get("env_file"), (backend.parent / ".env", backend / ".env"))

    def test_default_model_is_current_provider_replacement(self) -> None:
        self.assertEqual(self.load().gemini_model, "gemini-3.6-flash")
        self.assertFalse(self.load().ai_configured)

    def test_checked_in_example_is_blank(self) -> None:
        example = Path(config.__file__).parent / ".env.example"
        self.assertFalse(bool((dotenv_values(example).get("GEMINI_API_KEY") or "").strip()))

    def test_root_environment_is_loaded_when_backend_environment_is_absent(self) -> None:
        self.root_env.write_text("GEMINI_API_KEY=synthetic-root-key\nUNRELATED_SETTING=ignored\n")
        self.assertEqual(self.load().gemini_api_key.get_secret_value(), "synthetic-root-key")

    def test_backend_environment_overrides_root_environment(self) -> None:
        self.root_env.write_text("GEMINI_API_KEY=synthetic-root-key\nGEMINI_TIMEOUT_SECONDS=30\n")
        self.backend_env.write_text("GEMINI_API_KEY=synthetic-backend-key\n")
        settings = self.load()
        self.assertEqual(settings.gemini_api_key.get_secret_value(), "synthetic-backend-key")
        self.assertEqual(settings.gemini_timeout_seconds, 30)

    def test_blank_backend_key_intentionally_overrides_root_key(self) -> None:
        self.root_env.write_text("GEMINI_API_KEY=synthetic-root-key\n")
        self.backend_env.write_text("GEMINI_API_KEY=\n")
        self.assertFalse(self.load().ai_configured)

    def test_process_environment_overrides_both_files(self) -> None:
        self.root_env.write_text("GEMINI_API_KEY=synthetic-root-key\n")
        self.backend_env.write_text("GEMINI_API_KEY=synthetic-backend-key\n")
        with patch.dict(os.environ, GEMINI_API_KEY="synthetic-process-key"):
            self.assertEqual(self.load().gemini_api_key.get_secret_value(), "synthetic-process-key")

    def test_constructor_overrides_process_environment(self) -> None:
        with patch.dict(os.environ, GEMINI_API_KEY="synthetic-process-key"):
            settings = self.load(gemini_api_key=SecretStr("synthetic-constructor-key"))
        self.assertEqual(settings.gemini_api_key.get_secret_value(), "synthetic-constructor-key")
        self.assertNotIn("synthetic-constructor-key", repr(settings))


class GeminiConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        self.addAsyncCleanup(self.client.aclose)
        with patch.dict(Settings.model_config, env_file=None):
            self.settings = Settings(
                gemini_api_key=SecretStr(" synthetic-test-key "), gemini_model="gemini-3.6-flash"
            )
        self.service = GeminiService(self.settings, self.client)
        sleep = patch("backend.gemini.asyncio.sleep", new_callable=AsyncMock)
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    async def test_missing_key_mentions_both_files_without_network(self) -> None:
        self.settings.gemini_api_key = SecretStr(" ")
        for request in (self.service.chat(ChatRequest(message="Hello")),
                        self.service.translate(TranslationRequest(text="Bonjour"))):
            with self.assertRaises(AIError) as raised:
                await request
            self.assertEqual(raised.exception.status_code, 503)
            self.assertIn("backend/.env", raised.exception.detail)
            self.assertIn("root .env", raised.exception.detail)
            self.assertIn("restart", raised.exception.detail)
        self.assertEqual(self.requests, [])

    async def test_transient_unavailable_retries_same_model_without_exposing_key(self) -> None:
        self.responses = [
            httpx.Response(503, json={"error": {"message": "provider-private-response"}}),
            httpx.Response(200, json=generated("Hello!")),
        ]
        self.assertEqual(await self.service.chat(ChatRequest(message="Hello")), "Hello!")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0].url, self.requests[1].url)
        self.assertEqual(self.requests[0].content, self.requests[1].content)
        self.assertEqual(self.requests[0].headers["x-goog-api-key"], "synthetic-test-key")
        self.assertNotIn("synthetic-test-key", str(self.requests[0].url))
        self.assertNotIn("synthetic-test-key", self.requests[0].content.decode())
        self.sleep.assert_awaited_once()

    async def test_persistent_unavailable_is_bounded_and_sanitized(self) -> None:
        self.responses = [
            httpx.Response(503, json={"error": {"message": "provider-private-response"}})
            for _ in range(3)
        ]
        with self.assertRaises(AIError) as raised:
            await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("provider-private-response", raised.exception.detail)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.sleep.await_count, 2)

    async def test_translation_recovers_on_third_attempt_with_increasing_backoff(self) -> None:
        translation = {
            "translation": "Hello.", "explanation": "A greeting.",
            "vocabulary": [], "note": "Unreviewed AI suggestion.",
        }
        self.responses = [
            httpx.Response(503, json={"error": "provider-private-response"}),
            httpx.Response(503, json={"error": "provider-private-response"}),
            httpx.Response(200, json=generated(json.dumps(translation))),
        ]
        with patch("backend.gemini.random.random", return_value=0.5):
            with self.assertLogs("backend.gemini", level="WARNING") as captured:
                result = await self.service.translate(TranslationRequest(
                    text="Bonjour.", source_language="fr", target_language="en",
                    use_dataset=False, use_dictionary=False,
                ))
        self.assertEqual(result.model_dump(), translation)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual([call.args[0] for call in self.sleep.await_args_list], [1.5, 2.5])
        for request in self.requests[1:]:
            self.assertEqual(request.url, self.requests[0].url)
            self.assertEqual(request.content, self.requests[0].content)
        logged = "\n".join(captured.output)
        self.assertIn("attempt 2 of 3", logged)
        self.assertIn("attempt 3 of 3", logged)
        self.assertNotIn("provider-private-response", logged)
        self.assertNotIn("synthetic-test-key", logged)

    async def test_provider_quota_error_stops_remaining_retries(self) -> None:
        self.responses = [httpx.Response(503), httpx.Response(429)]
        with self.assertRaises(AIError) as raised:
            await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(len(self.requests), 2)
        self.sleep.assert_awaited_once()

    async def test_retry_wait_is_inside_total_request_timeout(self) -> None:
        async def delayed_retry(_: float) -> None:
            await asyncio.Event().wait()

        self.settings.gemini_timeout_seconds = 1
        self.responses = [httpx.Response(503, json={"error": "provider-private-response"})]
        self.sleep.side_effect = delayed_retry
        async with asyncio.timeout(2):
            with self.assertRaises(AIError) as raised:
                await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(len(self.requests), 1)
        self.sleep.assert_awaited_once()

    async def test_second_backoff_uses_the_same_total_request_timeout(self) -> None:
        waits = 0

        async def delayed_second_retry(_: float) -> None:
            nonlocal waits
            waits += 1
            if waits == 2:
                await asyncio.Event().wait()

        self.settings.gemini_timeout_seconds = 1
        self.responses = [httpx.Response(503), httpx.Response(503)]
        self.sleep.side_effect = delayed_second_retry
        async with asyncio.timeout(2):
            with self.assertRaises(AIError) as raised:
                await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.sleep.await_count, 2)

    async def test_network_failure_is_sanitized_without_retry(self) -> None:
        with patch.object(self.client, "post", side_effect=httpx.ConnectError("provider-private-response")):
            with self.assertRaises(AIError) as raised:
                await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("provider-private-response", raised.exception.detail)
        self.sleep.assert_not_awaited()

    async def test_model_not_found_is_actionable_without_retry(self) -> None:
        self.responses = [httpx.Response(404, json={"error": {"message": "provider-private-response"}})]
        with self.assertRaises(AIError) as raised:
            await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("GEMINI_MODEL", raised.exception.detail)
        self.assertIn("unavailable", raised.exception.detail)
        self.assertIn("restart", raised.exception.detail)
        self.assertNotIn("provider-private-response", raised.exception.detail)
        self.assertEqual(len(self.requests), 1)
        self.sleep.assert_not_awaited()

    async def test_auth_and_quota_errors_do_not_retry(self) -> None:
        for provider, status in ((400, 502), (401, 503), (403, 503), (429, 429)):
            with self.subTest(provider=provider):
                self.responses = [httpx.Response(provider, json={"error": "provider-private-response"})]
                with self.assertRaises(AIError) as raised:
                    await self.service.chat(ChatRequest(message="Hello"))
                self.assertEqual(raised.exception.status_code, status)
                self.assertNotIn("provider-private-response", raised.exception.detail)
                self.sleep.assert_not_awaited()
        self.assertEqual(len(self.requests), 4)

    async def test_translation_contract_still_uses_structured_content(self) -> None:
        translation = {"translation": "Salut!", "explanation": "A greeting.", "vocabulary": [], "note": ""}
        self.responses = [httpx.Response(200, json=generated(json.dumps(translation)))]
        result = await self.service.translate(TranslationRequest(text="Bonjour"))
        self.assertEqual(result.model_dump(), translation)
        sent = json.loads(self.requests[0].content)
        self.assertEqual(sent["contents"], [{"role": "user", "parts": [{"text": "Bonjour"}]}])
        self.assertEqual(sent["generationConfig"]["responseMimeType"], "application/json")

    async def test_truncated_content_is_never_returned_as_success(self) -> None:
        self.responses = [httpx.Response(200, json=generated("partial", "MAX_TOKENS"))]
        with self.assertRaises(AIError) as raised:
            await self.service.chat(ChatRequest(message="Hello"))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("cut short", raised.exception.detail)
        self.sleep.assert_not_awaited()

    async def test_coursework_tutor_sends_only_supplied_context_and_question(self) -> None:
        context = json.dumps({
            "grammar": {"S": [["hello"]]},
            "first": {"S": ["hello"]},
            "follow": {"S": ["$"]},
            "parse_result": {"accepted": True},
            "practice_text": "hello",
        })
        for language, expected_language in (("fr", "French"), ("en", "English")):
            with self.subTest(language=language):
                self.responses = [httpx.Response(200, json=generated("A compiler explanation."))]
                result = await self.service.explain_coursework("Why is hello accepted?", language, context)
                self.assertEqual(result, "A compiler explanation.")
                sent = json.loads(self.requests[-1].content)
                self.assertEqual(sent["contents"], [{
                    "role": "user",
                    "parts": [
                        {"text": f"Coursework context (JSON data):\n{context}"},
                        {"text": "Question:\nWhy is hello accepted?"},
                    ],
                }])
                instruction = sent["systemInstruction"]["parts"][0]["text"]
                for topic in ("lexing", "CFG", "FIRST", "FOLLOW", "LL(1)", "left recursion", "left factoring"):
                    self.assertIn(topic, instruction)
                self.assertIn(f"Explain in {expected_language}", instruction)
                self.assertIn("authoritative", instruction)
                self.assertIn("not instructions", instruction)
                self.assertIn("saved grammar", instruction)
                self.assertIn("fieldwork", instruction)
                self.assertNotIn("responseSchema", sent["generationConfig"])
                self.assertNotIn("responseMimeType", sent["generationConfig"])

    async def test_coursework_tutor_response_length_matches_chat_contract(self) -> None:
        self.responses = [httpx.Response(200, json=generated("x" * 4000))]
        self.assertEqual(len(await self.service.explain_coursework("Hello", "en", "{}")), 4000)
        self.responses = [httpx.Response(200, json=generated("x" * 4001))]
        with self.assertRaises(AIError) as raised:
            await self.service.explain_coursework("Hello", "en", "{}")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            raised.exception.detail, "Gemini's answer is too long. Please ask a more focused question."
        )

    async def test_coursework_tutor_propagates_provider_errors_without_fallback(self) -> None:
        for provider, body, expected in (
            (429, {"error": "provider-private-response"}, 429),
            (200, generated("partial", "MAX_TOKENS"), 502),
            (200, generated("", "SAFETY"), 422),
        ):
            with self.subTest(provider=provider, expected=expected):
                self.responses = [httpx.Response(provider, json=body)]
                with self.assertRaises(AIError) as raised:
                    await self.service.explain_coursework("Hello", "en", "{}")
                self.assertEqual(raised.exception.status_code, expected)
                self.assertNotIn("provider-private-response", raised.exception.detail)

    async def test_coursework_tutor_requires_key_without_network(self) -> None:
        self.settings.gemini_api_key = SecretStr("")
        with self.assertRaises(AIError) as raised:
            await self.service.explain_coursework("Hello", "en", "{}")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
