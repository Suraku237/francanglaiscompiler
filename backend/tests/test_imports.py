import base64
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.config import Settings
from backend.import_models import MAX_FILE_BYTES
from backend.imports import split_segments
from backend.main import create_app
from data_collector import dataset


def pdf_bytes(text: bool = True, pages: int = 1, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(595, 842)
        if text:
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 72 720 Td (Cameroon language sample.) Tj ET")
            page[NameObject("/Contents")] = stream
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }),
                }),
            })
    if encrypted:
        writer.encrypt("local-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx_bytes(xml: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml or (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Bonjour</w:t><w:tab/><w:t>Cameroon</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Second line.</w:t></w:r></w:p></w:body></w:document>'
        ))
    return output.getvalue()


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(dataset, "DATASET_PATH", str(self.directory / "dataset.csv")))
        self.stack.enter_context(patch.object(dataset, "AUDIO_DIR", str(self.directory / "audio")))
        dataset.ensure_dataset_file()
        self.original_csv = Path(dataset.DATASET_PATH).read_bytes()
        self.original_files = {path.name for path in self.directory.iterdir() if path.is_file()}
        self.requests: list[httpx.Request] = []
        self.response_text = "Sample machine transcript."
        self.finish = "STOP"
        self.provider_status = 200
        settings = Settings(gemini_api_key=SecretStr("test-key-not-real"), gemini_timeout_seconds=5)
        self.client = self.stack.enter_context(TestClient(create_app(settings, transport=httpx.MockTransport(self.respond))))

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.provider_status, json={
            "candidates": [{"finishReason": self.finish, "content": {"parts": [{"text": self.response_text}]}}],
        })

    def upload(self, name: str, content: bytes, *, consent: str = "false") -> httpx.Response:
        return self.client.post("/api/imports/preview", files={"file": (name, content)}, data={"allow_cloud_processing": consent})

    def assert_nothing_saved(self) -> None:
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), self.original_csv)
        self.assertEqual({path.name for path in self.directory.iterdir() if path.is_file()}, self.original_files)

    def test_local_utf8_preview_preserves_words_and_never_calls_ai(self) -> None:
        text = "Ça va ?\r\nI di waka.\n"
        response = self.upload("conversation.txt", text.encode("utf-8-sig"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], text)
        self.assertEqual(response.json()["method"], "local")
        self.assertEqual(self.requests, [])
        self.assert_nothing_saved()

    def test_segments_preserve_all_input_without_truncation(self) -> None:
        for text in ("word " * 3000, "a" * 9100, "line one\nline two\n" * 600):
            segments = split_segments(text)
            self.assertEqual("".join(segments), text)
            self.assertTrue(all(0 < len(part) <= 4000 for part in segments))
        response = self.upload("long.txt", b"a" * 40001)
        self.assertEqual(response.status_code, 413)

    def test_dataset_csv_alignment_is_previewed_without_inherited_approval(self) -> None:
        csv_text = "text,language,english_gloss,review_status\nmbolo,francanglais,hello,approved\n"
        response = self.upload("words.csv", csv_text.encode())
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["drafts"][0]
        self.assertEqual((draft["text"], draft["english_gloss"], draft["language"]), ("mbolo", "hello", "francanglais"))
        self.assertEqual(draft["review_status"], "unreviewed")
        self.assertEqual(self.requests, [])
        self.assert_nothing_saved()

    def test_json_dataset_preview_supports_legacy_unknown_language(self) -> None:
        response = self.upload("words.json", json.dumps({"entries": [{"text": "sample", "french_gloss": "exemple", "contributor": "PRIVATE"}]}).encode())
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["drafts"][0]
        self.assertEqual(draft["language"], "unspecified")
        self.assertNotIn("contributor", draft)
        self.assert_nothing_saved()

    def test_invalid_structured_files_are_not_silently_imported(self) -> None:
        for name, contents in (
            ("broken.json", b"{not json}"),
            ("broken.json", b'{"entries": "not an array"}'),
            ("broken.csv", b"text,text\none,two"),
            ("broken.csv", b"text,language\none,pidgin,extra"),
            ("broken.csv", b"text,language\none"),
            ("broken.json", b'[{"text": "one", "language": "de"}]'),
            ("broken.json", b'{"entries": [{"text": " "}]}'),
        ):
            with self.subTest(name=name, contents=contents):
                response = self.upload(name, contents)
                self.assertEqual(response.status_code, 422, response.text)
        response = self.upload("large.json", json.dumps([{"text": "word"}] * 101).encode())
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.requests, [])

    def test_pdf_text_is_local_and_scans_require_consent(self) -> None:
        response = self.upload("source.pdf", pdf_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Cameroon language sample.", response.json()["text"])
        self.assertEqual(response.json()["method"], "local")
        self.assertEqual(self.upload("scan.pdf", pdf_bytes(text=False)).status_code, 422)
        self.assertEqual(self.requests, [])
        response = self.upload("scan.pdf", pdf_bytes(text=False), consent="true")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["method"], "gemini")
        self.assertEqual(self.requests[-1].headers["x-goog-api-key"], "test-key-not-real")

    def test_pdf_limits_and_encryption_are_explicit(self) -> None:
        for data, status in ((pdf_bytes(pages=41), 413), (pdf_bytes(encrypted=True), 422), (b"%PDF-1.7\nbroken", 422)):
            self.assertEqual(self.upload("source.pdf", data).status_code, status)
        self.assertEqual(self.requests, [])

    def test_mixed_pdf_discloses_missing_text_and_uses_ocr_only_with_consent(self) -> None:
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(pdf_bytes())))
        writer.add_blank_page(595, 842)
        output = io.BytesIO()
        writer.write(output)
        response = self.upload("mixed.pdf", output.getvalue())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("no text layer", " ".join(response.json()["warnings"]))
        self.assertEqual(self.requests, [])
        response = self.upload("mixed.pdf", output.getvalue(), consent="true")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["method"], "gemini")
        self.assertEqual(response.json()["text"], self.response_text)

    def test_docx_body_paragraphs_and_tabs_are_preserved(self) -> None:
        response = self.upload("notes.docx", docx_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], "Bonjour\tCameroon\nSecond line.")
        self.assertTrue(response.json()["warnings"])
        self.assertEqual(self.requests, [])

    def test_docx_entities_and_bombs_rejected(self) -> None:
        self.assertEqual(self.upload("bad.docx", b"not a zip").status_code, 422)
        self.assertEqual(self.upload("entities.docx", docx_bytes('<!DOCTYPE x [<!ENTITY x "data">]><x>&x;</x>')).status_code, 422)
        self.assertEqual(self.upload("bomb.docx", docx_bytes("<x>" + "a" * (4 * 1024 * 1024) + "</x>")).status_code, 413)

    def test_all_advertised_media_formats_require_consent_and_use_inline_data(self) -> None:
        payloads = {
            "sample.mp3": b"ID3sample", "sample.wav": b"RIFF0000WAVEsample",
            "sample.m4a": b"0000ftypM4A sample", "sample.ogg": b"OggSsample",
            "sample.flac": b"fLaCsample", "sample.mp4": b"0000ftypisomsample",
            "sample.mov": b"0000ftypqt  sample", "sample.webm": b"\x1a\x45\xdf\xa3sample",
        }
        for extension, image_format in (("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP")):
            output = io.BytesIO()
            Image.new("RGB", (8, 8), "white").save(output, image_format)
            payloads["image." + extension] = output.getvalue()
        for name, data in payloads.items():
            with self.subTest(name=name):
                before = len(self.requests)
                self.assertEqual(self.upload(name, data).status_code, 422)
                self.assertEqual(len(self.requests), before)
                response = self.upload(name, data, consent="true")
                self.assertEqual(response.status_code, 200, response.text)
                sent = json.loads(self.requests[-1].content)
                self.assertEqual(base64.b64decode(sent["contents"][0]["parts"][1]["inline_data"]["data"]), data)
                self.assertNotIn("file_data", json.dumps(sent))
                self.assertEqual(response.json()["method"], "gemini")
        self.assert_nothing_saved()

    def test_media_spoofing_empty_files_and_unsupported_formats(self) -> None:
        for name, contents, status in (
            ("fake.mp3", b"not mp3", 422), ("fake.png", b"MZ executable", 422),
            ("fake.pdf", b"not pdf", 422), ("empty.txt", b"", 422),
            ("empty.txt", b" \n", 422), ("binary.txt", b"a\x00b", 422),
            ("latin.txt", b"\xff\xfe", 422), ("unknown.exe", b"data", 415),
        ):
            self.assertEqual(self.upload(name, contents, consent="true").status_code, status)
        self.assertEqual(self.requests, [])

    def test_upload_size_and_consent_validation(self) -> None:
        self.assertEqual(self.upload("notes.txt", b"a" * (MAX_FILE_BYTES + 1)).status_code, 413)
        self.assertEqual(self.upload("notes.txt", b"text", consent="yes").status_code, 422)
        self.assertEqual(self.client.post("/api/imports/preview", data={"allow_cloud_processing": "true"}).status_code, 422)
        response = self.client.post("/api/imports/preview", content=b"", headers={"content-length": str(MAX_FILE_BYTES + 65537)})
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/imports/preview", files=[("file", ("a.txt", b"one")), ("file", ("b.txt", b"two"))])
        self.assertEqual(response.status_code, 400)
        response = self.upload("a" * 220 + ".txt", b"hello")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(len(response.json()["filename"]), 200)

    def test_ai_cutoff_and_empty_transcripts_are_failures(self) -> None:
        self.finish = "MAX_TOKENS"
        self.assertEqual(self.upload("sample.mp3", b"ID3sample", consent="true").status_code, 502)
        self.finish = "STOP"
        self.response_text = "[NO_TEXT]"
        self.assertEqual(self.upload("sample.mp3", b"ID3sample", consent="true").status_code, 422)
        self.assert_nothing_saved()

    def test_chunked_upload_is_bounded_without_content_length(self) -> None:
        def chunks():
            yield b'--mboa\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n\r\n'
            for _ in range(194):
                yield b"a" * 65536
            yield b"\r\n--mboa--\r\n"

        response = self.client.post(
            "/api/imports/preview", content=chunks(),
            headers={"content-type": "multipart/form-data; boundary=mboa"},
        )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(self.requests, [])

    def test_openapi_describes_file_and_explicit_cloud_consent(self) -> None:
        operation = self.client.get("/openapi.json").json()["paths"]["/api/imports/preview"]["post"]
        schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
        self.assertEqual(schema["properties"]["file"]["format"], "binary")
        self.assertEqual(schema["properties"]["allow_cloud_processing"]["default"], "false")

    def test_suggestions_quote_reviewed_text_and_do_not_save(self) -> None:
        self.response_text = json.dumps({"drafts": [{"text": "waka", "language": "pidgin", "entry_type": "Word", "english_gloss": "walk", "lexical_category": "VERB"}]})
        response = self.client.post("/api/imports/suggest", json={"text": "I di waka.", "language": "pidgin"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["drafts"][0]["review_status"], "unreviewed")
        sent = json.loads(self.requests[-1].content)
        self.assertEqual(sent["contents"][0]["parts"][0]["text"], "I di waka.")
        self.assert_nothing_saved()

    def test_invented_subword_approved_duplicate_and_invalid_ai_drafts_fail(self) -> None:
        for drafts in (
            [{"text": "invented"}], [{"text": "wa"}],
            [{"text": "waka", "review_status": "approved"}],
            [{"text": "waka"}, {"text": "waka"}],
            [{"text": "waka", "lexical_category": "MAGIC"}],
        ):
            self.response_text = json.dumps({"drafts": drafts})
            response = self.client.post("/api/imports/suggest", json={"text": "I di waka.", "language": "pidgin"})
            self.assertEqual(response.status_code, 502, response.text)
        self.assert_nothing_saved()

    def test_changed_approved_evidence_requires_explicit_reapproval(self) -> None:
        created = self.client.post("/api/dataset", json={
            "text": "Test expression", "language": "pidgin", "english_gloss": "test meaning",
            "review_status": "approved",
        }).json()
        endpoint = "/api/dataset/" + created["id"]
        unchanged = self.client.patch(endpoint, json={"english_gloss": "test meaning"})
        self.assertEqual(unchanged.json()["review_status"], "approved")
        changed = self.client.patch(endpoint, json={"english_gloss": "different meaning"})
        self.assertEqual(changed.json()["review_status"], "unreviewed")
        lookup = self.client.post("/api/translate", json={
            "text": "Test expression", "source_language": "pidgin",
            "target_language": "en", "allow_ai": False,
        })
        self.assertEqual(lookup.status_code, 422)
        approved = self.client.patch(endpoint, json={"english_gloss": "reviewed meaning", "review_status": "approved"})
        self.assertEqual(approved.json()["review_status"], "approved")
        self.assertEqual(self.requests, [])

    def test_desktop_edits_cannot_inherit_approval_of_old_wording(self) -> None:
        created = self.client.post("/api/dataset", json={
            "text": "Test expression", "language": "pidgin", "english_gloss": "meaning",
            "review_status": "approved",
        }).json()
        dataset.update_entry(created["id"], {"text": "Changed test expression"})
        self.assertEqual(dataset.load_all()[0]["review_status"], "unreviewed")

    def test_full_review_can_edit_metadata_of_existing_legacy_duplicates(self) -> None:
        created = self.client.post("/api/dataset", json={"text": "Repeated legacy expression"}).json()
        dataset.append_entry({**created, "id": "historical-duplicate"})
        changes = {key: value for key, value in created.items() if key not in ("id", "timestamp", "audio_filename")}
        changes["notes"] = "Review context added without changing the expression."
        response = self.client.patch("/api/dataset/" + created["id"], json=changes)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["notes"], changes["notes"])


if __name__ == "__main__":
    unittest.main()
