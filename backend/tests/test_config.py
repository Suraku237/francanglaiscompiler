import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from backend import config
from backend.auth import AuthSettings, AuthStore
from backend.config import Settings
from backend.main import create_app


class CompilerSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory(prefix=".config-test-", dir=Path(__file__).parent)
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root_env = root / ".env"
        self.backend_env = root / "backend.env"

    def load(self, **values) -> Settings:
        with patch.dict(Settings.model_config, env_file=(self.root_env, self.backend_env)):
            return Settings(**values)

    def test_default_environment_paths_are_absolute_and_backend_is_last(self) -> None:
        backend = Path(config.__file__).resolve().parent
        self.assertEqual(Settings.model_config.get("env_file"), (backend.parent / ".env", backend / ".env"))

    def test_settings_only_configure_cors_not_generation(self) -> None:
        settings = self.load()
        self.assertEqual(set(Settings.model_fields), {"cors_origins"})
        self.assertEqual(settings.cors_origins, ["http://localhost:5173", "http://127.0.0.1:5173"])
        for name in ("gemini_api_key", "gemini_model", "gemini_timeout_seconds", "ai_configured"):
            self.assertFalse(hasattr(settings, name), name)

    def test_obsolete_provider_values_are_ignored_from_files_environment_and_constructor(self) -> None:
        self.root_env.write_text(
            "GEMINI_API_KEY=synthetic-root-key\nGEMINI_TIMEOUT_SECONDS=not-a-number\n",
            encoding="utf-8",
        )
        self.backend_env.write_text("GEMINI_MODEL=retired-model\nUNRELATED_SETTING=ignored\n", encoding="utf-8")
        with patch.dict(os.environ, GEMINI_API_KEY="synthetic-process-key", GOOGLE_API_KEY="obsolete"):
            settings = self.load(gemini_api_key="synthetic-constructor-key", gemini_timeout_seconds=-1)
        self.assertEqual(set(settings.model_dump()), {"cors_origins"})
        self.assertNotIn("synthetic", repr(settings))
        self.assertNotIn("retired-model", settings.model_dump_json())

    def test_cors_settings_keep_environment_precedence(self) -> None:
        self.root_env.write_text('CORS_ORIGINS=["https://root.example"]\n', encoding="utf-8")
        self.assertEqual(self.load().cors_origins, ["https://root.example"])
        self.backend_env.write_text('CORS_ORIGINS=["https://backend.example"]\n', encoding="utf-8")
        self.assertEqual(self.load().cors_origins, ["https://backend.example"])
        with patch.dict(os.environ, CORS_ORIGINS='["https://process.example"]'):
            self.assertEqual(self.load().cors_origins, ["https://process.example"])
            self.assertEqual(self.load(cors_origins=["https://constructor.example"]).cors_origins,
                             ["https://constructor.example"])

    def test_checked_in_example_has_no_provider_or_ai_quota_configuration(self) -> None:
        example = dotenv_values(Path(config.__file__).parent / ".env.example")
        self.assertFalse(any(name.startswith(("GEMINI_", "GOOGLE_API_", "MBOA_AI_")) for name in example))

    def test_auth_has_no_generation_allowance_but_retains_normal_throttling(self) -> None:
        with patch.dict(AuthSettings.model_config, env_file=None), patch.dict(
            os.environ, MBOA_AI_DAILY_USER_LIMIT="invalid", MBOA_AI_DAILY_GLOBAL_LIMIT="invalid",
        ):
            settings = AuthSettings()
        self.assertFalse(any(name.startswith("ai_") for name in AuthSettings.model_fields))
        self.assertFalse(hasattr(settings, "ai_daily_user_limit"))
        self.assertFalse(hasattr(AuthStore, "charge_ai"))
        self.assertTrue(callable(AuthStore.throttle))

    def test_application_defaults_enable_authenticated_coursework_without_ai_transport(self) -> None:
        parameters = inspect.signature(create_app).parameters
        self.assertTrue(parameters["include_academic"].default)
        self.assertTrue(parameters["require_auth"].default)
        self.assertNotIn("transport", parameters)
        self.assertIn("auth_transport", parameters)

    def test_production_forbids_unauthenticated_mode_but_permits_authenticated_coursework(self) -> None:
        with patch.dict(AuthSettings.model_config, env_file=None):
            accounts = AuthSettings(
                environment="production", data_dir=self.root_env.parent / "accounts",
                public_url="https://compiler.example", mail_mode="smtp",
                smtp_host="smtp.example", mail_from="compiler@example.com",
            )
        with self.assertRaisesRegex(ValueError, "Authentication cannot be disabled"):
            create_app(self.load(), require_auth=False, auth_settings=accounts)
        with patch("backend.main.install_web") as install_web:
            app = create_app(self.load(), auth_settings=accounts, mailer=lambda *_args: None)
        self.assertTrue(install_web.call_args.kwargs["production"])
        self.assertIsNotNone(app.state.auth_store)
        self.assertIn("/api/coursework", app.openapi()["paths"])
        self.assertIsNone(app.openapi_url)


if __name__ == "__main__":
    unittest.main()
