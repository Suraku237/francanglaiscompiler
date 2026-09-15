"""Local HTTP server for the web interface.

Serves the static files in ``web/`` and exposes the analyzer over one JSON endpoint.
Standard library only, and bound to the loopback interface: this is a demonstration
front end for the compiler, not a public service.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .analysis import analyse
from .generate import Generator
from .grammar import load_grammar
from .langid import profile
from .lexer import Lexer
from .lexicon import ROOT, load_lexicon, normalize
from .parser import LL1Parser
from .tokens import Cat, Lang
from .translate import Translator

WEB_DIR = ROOT / "web"
GRAMMAR_FILE = ROOT / "grammar" / "fca.gram"

MAX_BODY = 16 * 1024
MAX_TEXT = 2000

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

_LANGUAGE_NAMES = {
    Lang.CAMFRANGLAIS: "Camfranglais",
    Lang.FRENCH: "French",
    Lang.ENGLISH: "English",
    Lang.UNKNOWN: "Unrecognised",
}


class Analyzer:
    """One shared lexicon, one parser, one scanner per language preference."""

    def __init__(self) -> None:
        self.lexicon = load_lexicon()
        self.grammar = load_grammar(GRAMMAR_FILE)
        self.parser = LL1Parser(self.grammar, analyse(self.grammar))
        self._lexers: dict[str, Lexer] = {}
        self._translators: dict[str, Translator] = {}
        lexer, _ = self._for("")
        self.generator = Generator(self.grammar, self.lexicon, lexer, self.parser)

    def _for(self, prefer: str) -> tuple[Lexer, Translator]:
        key = (prefer or "").lower()
        if key not in self._lexers:
            lang = Lang[key.upper()] if key in {"camfranglais", "french"} else None
            lexer = Lexer(self.lexicon, lang)
            self._lexers[key] = lexer
            self._translators[key] = Translator(self.lexicon, lexer)
        return self._lexers[key], self._translators[key]

    def sample(self, prefer: str = "") -> str:
        key = (prefer or "").lower()
        lang = Lang[key.upper()] if key in {"camfranglais", "french"} else None
        return self.generator.sentence(lang)

    def analyze(self, text: str, prefer: str = "") -> dict:
        lexer, translator = self._for(prefer)
        tokens = lexer.tokenize(text)
        parsed = self.parser.parse(tokens)
        result = translator.translate_tokens(tokens, text)
        mixture = profile(tokens)

        return {
            "text": text,
            "mixture": {
                "label": mixture.label,
                "dominant": _LANGUAGE_NAMES.get(mixture.dominant, "Unrecognised"),
                "total": mixture.total,
                "shared": mixture.shared,
                "unknown": round(mixture.unknown_rate),
                "shares": [
                    {"language": _LANGUAGE_NAMES.get(lang, lang.value), "percent": round(pct)}
                    for lang, pct in sorted(mixture.percentages.items(), key=lambda kv: -kv[1])
                ],
            },
            "tokens": [
                {
                    "lexeme": tok.surface,
                    "category": tok.cat.value,
                    "language": _LANGUAGE_NAMES.get(tok.lang, tok.lang.value),
                    "gloss": tok.gloss,
                    "section": tok.section,
                }
                for tok in tokens
                if tok.cat is not Cat.PUNCT
            ],
            "syntax": {
                "accepted": parsed.accepted,
                "categories": [tok.cat.value for tok in tokens],
                "error": parsed.error,
                "expected": list(parsed.expected),
                "tree": parsed.tree.render() if parsed.tree else "",
                "steps": len(parsed.trace),
            },
            "translation": {
                "english": result.english,
                "notes": list(dict.fromkeys(result.notes)),
            },
            "readings": self._readings(text, translator),
        }

    @staticmethod
    def _readings(text: str, translator: Translator) -> list[dict]:
        """Dictionary readings, shown when the user typed a single word."""
        key = normalize(text)
        if not key or " " in key:
            return []
        return [
            {"language": lang.title(), "category": cat, "english": english}
            for lang, cat, english in translator.translate_word(key)
        ]


class Handler(BaseHTTPRequestHandler):
    server_version = "francanglais"
    analyzer: Analyzer

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        target = WEB_DIR / "index.html" if path == "/" else WEB_DIR / path.lstrip("/")
        try:
            resolved = target.resolve(strict=True)
            resolved.relative_to(WEB_DIR.resolve())
        except (OSError, ValueError):
            return self._send_text(404, "not found")
        if not resolved.is_file():
            return self._send_text(404, "not found")

        body = resolved.read_bytes()
        content_type = CONTENT_TYPES.get(resolved.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route not in {"/api/analyze", "/api/sample"}:
            return self._send_json(404, {"error": "unknown endpoint"})

        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY:
            return self._send_json(413, {"error": "request too large"})
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._send_json(400, {"error": "malformed request"})

        prefer = str(payload.get("prefer", ""))

        if route == "/api/sample":
            try:
                return self._send_json(200, {"text": self.analyzer.sample(prefer)})
            except Exception:
                return self._send_json(500, {"error": "Could not generate a sentence."})

        text = str(payload.get("text", "")).strip()[:MAX_TEXT]
        if not text:
            return self._send_json(400, {"error": "Enter some text first."})

        try:
            result = self.analyzer.analyze(text, prefer)
        except Exception:  # a bad utterance must not take the server down
            return self._send_json(500, {"error": "The analyzer could not read that."})
        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {self.address_string()} {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    print("loading dictionaries ...")
    Handler.analyzer = Analyzer()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Franc-anglais compiler running at http://{host}:{port}/  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
