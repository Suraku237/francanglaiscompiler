import io
import json
import unittest
from pathlib import Path

import httpx
from PIL import Image
from pypdf import PdfReader, PdfWriter

from backend.import_models import MAX_EXTRACTED_TEXT, MAX_FILE_BYTES
from backend.imports import split_segments
from backend.tests.import_fixtures import docx_bytes, pdf_bytes
from backend.tests.test_api import ApiTestCase
from data_collector import dataset


class ImportTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        dataset.ensure_dataset_file()
        self.original_csv = Path(dataset.DATASET_PATH).read_bytes()
        self.original_files = {path.name for path in self.directory.iterdir() if path.is_file()}

    def upload(self, name: str, content: bytes) -> httpx.Response:
        return self.client.post("/api/imports/preview", files={"file": (name, content)})

    def assert_nothing_saved(self) -> None:
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), self.original_csv)
        self.assertEqual({path.name for path in self.directory.iterdir() if path.is_file()}, self.original_files)
        self.assert_no_outbound_http()

    def test_local_utf8_preview_preserves_words_and_never_calls_ai(self) -> None:
        text = "Ça va ?\r\nI di waka.\n"
        response = self.upload("conversation.txt", text.encode("utf-8-sig"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], text)
        self.assertEqual(response.json()["method"], "local")
        self.assert_no_outbound_http()
        self.assert_nothing_saved()

    def test_segments_preserve_all_input_without_truncation(self) -> None:
        for text in ("word " * 3000, "a" * 9100, "line one\nline two\n" * 600):
            segments = split_segments(text)
            self.assertEqual("".join(segments), text)
            self.assertTrue(all(0 < len(part) <= 4000 for part in segments))
        response = self.upload("long.txt", b"a" * 40001)
        self.assertEqual(response.status_code, 413)

    def test_dataset_csv_alignment_is_previewed_without_inherited_approval(self) -> None:
        csv_text = (
            "text,language,english_gloss,review_status,category,source_location,contributor,notes\n"
            'mbolo,francanglais,hello,approved,Campus Life,  Campus  ,Collector,"  Original\nnotes  "\n'
        )
        response = self.upload("words.csv", csv_text.encode())
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["drafts"][0]
        self.assertEqual((draft["text"], draft["english_gloss"], draft["language"]), ("mbolo", "hello", "francanglais"))
        self.assertEqual(draft["review_status"], "unreviewed")
        self.assertEqual(draft["category"], "Campus Life")
        self.assertEqual(draft["source_location"], "  Campus  ")
        self.assertEqual(draft["contributor"], "Collector")
        self.assertEqual(draft["notes"], "  Original\nnotes  ")
        self.assert_nothing_saved()

    def test_json_dataset_preview_supports_legacy_unknown_language(self) -> None:
        original = {
            "text": "  n’éko\tà  ", "french_gloss": "exemple", "contributor": "PRIVATE",
            "category": "Historical topic", "source_location": "  Original location  ",
            "notes": "Original\r\nnotes", "review_status": "approved",
        }
        response = self.upload("words.json", json.dumps({"entries": [original]}).encode())
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["drafts"][0]
        self.assertEqual(draft["language"], "unspecified")
        self.assertEqual(draft["review_status"], "unreviewed")
        for field in ("text", "french_gloss", "contributor", "category", "source_location", "notes"):
            self.assertEqual(draft[field], original[field], field)
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
        self.assert_no_outbound_http()

    def test_pdf_text_is_local_and_scans_require_manual_transcription(self) -> None:
        response = self.upload("source.pdf", pdf_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Cameroon language sample.", response.json()["text"])
        self.assertEqual(response.json()["method"], "local")
        scanned = self.upload("scan.pdf", pdf_bytes(text=False))
        self.assertEqual(scanned.status_code, 422)
        self.assertIn("manual", scanned.json()["detail"].lower())
        self.assert_nothing_saved()

    def test_pdf_limits_and_encryption_are_explicit(self) -> None:
        for data, status in ((pdf_bytes(pages=41), 413), (pdf_bytes(encrypted=True), 422), (b"%PDF-1.7\nbroken", 422)):
            self.assertEqual(self.upload("source.pdf", data).status_code, status)
        self.assert_no_outbound_http()

    def test_pdf_character_limit_counts_only_separators_between_pages(self) -> None:
        cases = [
            ["A" * (MAX_EXTRACTED_TEXT - 2)],
            ["A" * (MAX_EXTRACTED_TEXT - 1)],
            ["A" * MAX_EXTRACTED_TEXT],
            ["A" * 20_000, "B" * 19_998],
            ["", "B" * (MAX_EXTRACTED_TEXT - 2)],
            ["A" * (MAX_EXTRACTED_TEXT - 2), ""],
            ["A" * 19_997, "", "B" * 19_999],
        ]
        for pages in cases:
            expected = "\n\n".join(pages)
            with self.subTest(page_lengths=[len(page) for page in pages]):
                response = self.upload("boundary.pdf", pdf_bytes(page_texts=pages))
                self.assertEqual(response.status_code, 200, response.text)
                preview = response.json()
                self.assertEqual(preview["method"], "local")
                self.assertEqual(preview["text"], expected)
                self.assertEqual("".join(preview["segments"]), expected)
                self.assertTrue(all(0 < len(part) <= 4000 for part in preview["segments"]))
                self.assert_no_outbound_http()
        self.assert_nothing_saved()

    def test_pdf_character_limit_rejects_one_character_over_including_separators(self) -> None:
        cases = [
            ["A" * (MAX_EXTRACTED_TEXT + 1)],
            ["A" * 20_000, "B" * 19_999],
            ["", "A" * (MAX_EXTRACTED_TEXT - 1)],
            ["A" * (MAX_EXTRACTED_TEXT - 1), ""],
        ]
        for pages in cases:
            with self.subTest(page_lengths=[len(page) for page in pages]):
                self.assertEqual(len("\n\n".join(pages)), MAX_EXTRACTED_TEXT + 1)
                response = self.upload("too-long.pdf", pdf_bytes(page_texts=pages))
                self.assertEqual(response.status_code, 413, response.text)
                self.assertIn("40,000 characters", response.json()["detail"])
                self.assert_no_outbound_http()
        self.assert_nothing_saved()

    def test_mixed_pdf_keeps_local_text_and_discloses_empty_pages(self) -> None:
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(pdf_bytes())))
        writer.add_blank_page(595, 842)
        output = io.BytesIO()
        writer.write(output)
        response = self.upload("mixed.pdf", output.getvalue())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["method"], "local")
        self.assertEqual(response.json()["text"], "Cameroon language sample.\n\n")
        self.assertIn("no text layer", " ".join(response.json()["warnings"]))
        self.assert_nothing_saved()

    def test_docx_body_paragraphs_and_tabs_are_preserved(self) -> None:
        response = self.upload("notes.docx", docx_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], "Bonjour\tCameroon\nSecond line.")
        self.assertTrue(response.json()["warnings"])
        self.assert_no_outbound_http()

    def test_docx_entities_and_bombs_rejected(self) -> None:
        self.assertEqual(self.upload("bad.docx", b"not a zip").status_code, 422)
        self.assertEqual(self.upload("entities.docx", docx_bytes('<!DOCTYPE x [<!ENTITY x "data">]><x>&x;</x>')).status_code, 422)
        self.assertEqual(self.upload("bomb.docx", docx_bytes("<x>" + "a" * (4 * 1024 * 1024) + "</x>")).status_code, 413)

    def test_images_audio_and_video_are_rejected_with_manual_transcription_guidance(self) -> None:
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
                response = self.upload(name, data)
                self.assertEqual(response.status_code, 415, response.text)
                self.assertIn("manual", response.json()["detail"].lower())
        self.assert_nothing_saved()

    def test_media_spoofing_empty_files_and_unsupported_formats(self) -> None:
        for name, contents, status in (
            ("fake.mp3", b"not mp3", 415), ("fake.png", b"MZ executable", 415),
            ("fake.pdf", b"not pdf", 422), ("empty.txt", b"", 422),
            ("empty.txt", b" \n", 422), ("binary.txt", b"a\x00b", 422),
            ("latin.txt", b"\xff\xfe", 422), ("unknown.exe", b"data", 415),
        ):
            self.assertEqual(self.upload(name, contents).status_code, status)
        self.assert_no_outbound_http()

    def test_upload_size_filename_and_exactly_one_file_validation(self) -> None:
        self.assertEqual(self.upload("notes.txt", b"a" * (MAX_FILE_BYTES + 1)).status_code, 413)
        self.assertEqual(self.client.post("/api/imports/preview", files={"wrong": ("notes.txt", b"text")}).status_code, 422)
        self.assertEqual(self.client.post("/api/imports/preview", data={}).status_code, 422)
        response = self.client.post("/api/imports/preview", content=b"", headers={"content-length": str(MAX_FILE_BYTES + 65537)})
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/imports/preview", files=[("file", ("a.txt", b"one")), ("file", ("b.txt", b"two"))])
        self.assertEqual(response.status_code, 400)
        response = self.upload("a" * 220 + ".txt", b"hello")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(len(response.json()["filename"]), 200)

    def test_cloud_consent_and_unknown_multipart_fields_are_rejected(self) -> None:
        for field, value in (
            ("allow_cloud_processing", "true"), ("allow_cloud_processing", "false"),
            ("allow_cloud_processing", "yes"), ("provider", "retired"),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/imports/preview", files={"file": ("notes.txt", b"Raw text")},
                    data={field: value},
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("Maximum number of fields is 0", response.json()["detail"])
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
        self.assert_no_outbound_http()

    def test_openapi_describes_one_local_file_without_consent_or_generation_schemas(self) -> None:
        specification = self.client.get("/openapi.json").json()
        operation = specification["paths"]["/api/imports/preview"]["post"]
        schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
        self.assertEqual(schema["properties"]["file"]["format"], "binary")
        self.assertEqual(set(schema["properties"]), {"file"})
        self.assertEqual(schema["required"], ["file"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("ImportEntry", specification["components"]["schemas"])
        self.assertNotIn("SuggestedEntry", specification["components"]["schemas"])
        self.assertNotIn("/api/imports/suggest", specification["paths"])

    def test_suggestion_endpoint_is_removed_without_saving(self) -> None:
        response = self.client.post("/api/imports/suggest", json={"text": "I di waka.", "language": "pidgin"})
        self.assertEqual(response.status_code, 404, response.text)
        self.assert_nothing_saved()

    def test_changed_approved_evidence_requires_explicit_reapproval(self) -> None:
        created = self.client.post("/api/dataset", json={
            "text": "zandolo", "language": "pidgin", "english_gloss": "test meaning",
            "entry_type": "Word", "lexical_category": "NOUN", "review_status": "approved",
        }).json()
        endpoint = "/api/dataset/" + created["id"]
        unchanged = self.client.patch(endpoint, json={"english_gloss": "test meaning"})
        self.assertEqual(unchanged.json()["review_status"], "approved")
        changed = self.client.patch(endpoint, json={"english_gloss": "different meaning"})
        self.assertEqual(changed.json()["review_status"], "unreviewed")
        analysis = self.client.post("/api/analyze", json={"text": "zandolo"})
        self.assertEqual(analysis.json()["tokens"][0]["category"], "UNKNOWN")
        approved = self.client.patch(endpoint, json={"english_gloss": "reviewed meaning", "review_status": "approved"})
        self.assertEqual(approved.json()["review_status"], "approved")
        self.assertEqual(self.client.post("/api/analyze", json={"text": "zandolo"}).json()["tokens"][0]["category"],
                         "NOUN")
        self.assert_no_outbound_http()

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
