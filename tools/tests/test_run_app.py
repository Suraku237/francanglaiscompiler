import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from tools.run_app import LaunchError, ensure_frontend, is_loopback, main


@dataclass
class TestSettings:
    environment: str = "development"
    public_url: str = "http://127.0.0.1:8000"
    model_fields_set: set[str] = field(default_factory=set)


class LauncherTests(unittest.TestCase):
    def test_loopback_check_does_not_trust_host_prefixes(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                self.assertTrue(is_loopback(host))
        for host in ("0.0.0.0", "192.168.1.1", "localhost.example", "127.0.0.1.example"):
            with self.subTest(host=host):
                self.assertFalse(is_loopback(host))

    def test_missing_build_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LaunchError, "--build"):
                ensure_frontend(Path(directory), build=False)

    def test_build_does_not_silently_install_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LaunchError, "npm ci"):
                ensure_frontend(Path(directory), build=True)

    def test_failed_build_is_not_treated_as_a_ready_website(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend" / "node_modules").mkdir(parents=True)
            with patch("tools.run_app.shutil.which", return_value="npm"), patch(
                "tools.run_app.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["npm"])
            ), self.assertRaisesRegex(LaunchError, "build failed"):
                ensure_frontend(root, build=True)

    def test_local_launch_uses_one_origin_and_no_trusted_proxy_headers(self):
        with patch("tools.run_app.load_settings", return_value=TestSettings()), patch(
            "tools.run_app.ensure_frontend"
        ), patch("uvicorn.run", autospec=True) as run, patch.dict(os.environ, {}, clear=False):
            self.assertEqual(main(["--port", "8019"]), 0)
            self.assertEqual(os.environ["MBOA_PUBLIC_URL"], "http://127.0.0.1:8019")
            self.assertEqual(run.call_args.kwargs["port"], 8019)
            self.assertFalse(run.call_args.kwargs["proxy_headers"])

    def test_explicit_public_url_is_not_overwritten(self):
        settings = TestSettings(model_fields_set={"public_url"})
        with patch("tools.run_app.load_settings", return_value=settings), patch(
            "tools.run_app.ensure_frontend"
        ), patch("uvicorn.run", autospec=True), patch.dict(os.environ, {"MBOA_PUBLIC_URL": "http://localhost:5173"}):
            self.assertEqual(main([]), 0)
            self.assertEqual(os.environ["MBOA_PUBLIC_URL"], "http://localhost:5173")

    def test_public_development_listening_and_production_reload_are_rejected(self):
        for settings, args in (
            (TestSettings(), ["--host", "0.0.0.0"]),
            (TestSettings(environment="production"), ["--reload"]),
        ):
            with self.subTest(args=args), patch(
                "tools.run_app.load_settings", return_value=settings
            ), patch("uvicorn.run", autospec=True) as run, redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(args), 1)
                run.assert_not_called()
                self.assertIn("Mboa could not start", output.getvalue())

    def test_invalid_ports_are_rejected(self):
        for value in ("0", "65536", "not-a-port"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                main(["--port", value])
            self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
