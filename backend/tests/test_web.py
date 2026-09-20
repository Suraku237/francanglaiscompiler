import logging
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.web import JSON_REQUEST_LIMIT, PrivateQueryFilter, install_web


class WebBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.frontend = Path(self.directory.name)
        self.frontend.joinpath("index.html").write_text("<h1>Mboa</h1>", encoding="utf-8")

    def client(self, production=False):
        app = FastAPI()

        @app.get("/api/health")
        def health():
            return {"status": "ok"}

        @app.post("/api/echo")
        async def echo(request: Request):
            return {"bytes": len(await request.body())}

        install_web(
            app, frontend_dir=self.frontend, production=production,
            public_url="https://workspace.example",
        )
        return TestClient(app, base_url="https://workspace.example")

    def test_frontend_and_api_are_served_together(self):
        with self.client() as client:
            self.assertEqual(client.get("/").text, "<h1>Mboa</h1>")
            response = client.get("/api/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
            self.assertEqual(response.headers["x-frame-options"], "DENY")
            self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_production_checks_hosts_and_sets_transport_policy(self):
        with self.client(production=True) as client:
            self.assertIn("max-age=", client.get("/").headers["strict-transport-security"])
            self.assertEqual(client.get("/", headers={"Host": "untrusted.example"}).status_code, 400)
            redirect = client.get("http://workspace.example/", follow_redirects=False)
            self.assertEqual(redirect.status_code, 307)
            self.assertEqual(redirect.headers["location"], "https://workspace.example/")

    def test_unknown_api_paths_are_404_but_known_paths_keep_405_and_allow(self):
        with self.client() as client:
            missing = client.put("/api/retired-route", json={})
            self.assertEqual(missing.status_code, 404)
            wrong_method = client.get("/api/echo")
            self.assertEqual(wrong_method.status_code, 405)
            self.assertEqual(wrong_method.headers["allow"], "POST")
            self.assertEqual(client.post("/api/health", json={}).status_code, 405)

    def test_body_limit_accepts_boundary_and_rejects_next_byte(self):
        with self.client() as client:
            accepted = client.post("/api/echo", content=b"x" * JSON_REQUEST_LIMIT)
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["bytes"], JSON_REQUEST_LIMIT)
            rejected = client.post("/api/echo", content=b"x" * (JSON_REQUEST_LIMIT + 1))
            self.assertEqual(rejected.status_code, 413)
            self.assertEqual(rejected.headers["cache-control"], "no-store")

    def test_streamed_body_cannot_bypass_the_limit(self):
        def chunks():
            yield b"x" * JSON_REQUEST_LIMIT
            yield b"x"

        with self.client() as client:
            response = client.post("/api/echo", content=chunks())
            self.assertEqual(response.status_code, 413)

    def test_invalid_lengths_and_oversized_urls_are_explicit_errors(self):
        with self.client() as client:
            for size in ("-1", "broken"):
                with self.subTest(size=size):
                    self.assertEqual(
                        client.post("/api/echo", content=b"", headers={"Content-Length": size}).status_code,
                        400,
                    )
            self.assertEqual(client.get("/api/health?token=" + "x" * 8193).status_code, 414)

    def test_static_serving_does_not_publish_adjacent_private_data(self):
        self.frontend.joinpath("assets").mkdir()
        self.frontend.joinpath("assets", "index.js").write_text("export {}", encoding="utf-8")
        with self.client() as client:
            self.assertEqual(client.get("/assets/index.js").status_code, 200)
            self.assertEqual(client.get("/.env").status_code, 404)
            self.assertEqual(client.get("/.mboa/auth.sqlite3").status_code, 404)

    def test_production_requires_an_existing_frontend_build(self):
        with self.assertRaisesRegex(ValueError, "frontend build"):
            install_web(
                FastAPI(), frontend_dir=self.frontend / "missing", production=True,
                public_url="https://workspace.example",
            )

    def test_access_logs_do_not_include_search_terms_or_oauth_codes(self):
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1", "GET", "/api/auth/google/callback?code=secret&state=private", "1.1", 302),
            None,
        )
        self.assertTrue(PrivateQueryFilter().filter(record))
        self.assertNotIn("secret", record.getMessage())
        self.assertNotIn("private", record.getMessage())
        self.assertIn("/api/auth/google/callback", record.getMessage())


if __name__ == "__main__":
    unittest.main()
