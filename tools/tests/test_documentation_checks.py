import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from tools.check_documentation import (
    application_classes, check_class_coverage, check_no_signature_fields, check_report_automata,
    check_report_page_count, check_report_screenshots, check_sequence_activations,
    declared_classes, image_fingerprint,
)


class DocumentationCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="mboa-doc-check-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "backend"
        source.mkdir()
        (source / "models.py").write_text(
            "class Entry:\n    pass\n\nclass Response:\n    pass\n", encoding="utf-8",
        )
        tests = source / "tests"
        tests.mkdir()
        (tests / "test_models.py").write_text("class TestFixture:\n    pass\n", encoding="utf-8")
        self.diagrams = self.root / "docs" / "diagrams"
        self.diagrams.mkdir(parents=True)
        (self.diagrams / "classes.puml").write_text(
            '@startuml\nclass "Entry" as Entry\nclass Response\n@enduml\n', encoding="utf-8",
        )
        self.inventory = self.diagrams / "class-coverage.json"
        self.inventory.write_text(json.dumps({
            "backend.models.Entry": ["classes"],
            "backend.models.Response": ["classes"],
        }), encoding="utf-8")

    def test_only_production_classes_are_counted(self) -> None:
        ignored = self.root / "data_collector" / "audio"
        ignored.mkdir(parents=True)
        (ignored / "attachment.py").write_text("class NotApplicationSource:\n    pass\n", encoding="utf-8")
        self.assertEqual(application_classes(self.root), {"backend.models.Entry", "backend.models.Response"})
        self.assertEqual(check_class_coverage(self.root), 2)

    def test_new_undocumented_class_fails_the_check(self) -> None:
        (self.root / "backend" / "added.py").write_text("class Added:\n    pass\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing=.*backend.added.Added"):
            check_class_coverage(self.root)

    def test_namedtuple_factories_include_import_aliases_and_annotations(self) -> None:
        (self.root / "backend" / "tokens.py").write_text(
            "from collections import namedtuple as record\n"
            "import collections as records\n"
            "Token = record('Token', ['text', 'category'])\n"
            "Pair: type = records.namedtuple('Pair', ['left', 'right'])\n",
            encoding="utf-8",
        )
        self.assertEqual(application_classes(self.root), {
            "backend.models.Entry", "backend.models.Response", "backend.tokens.Token", "backend.tokens.Pair",
        })

    def test_unrelated_namedtuple_function_is_not_claimed_as_a_class(self) -> None:
        (self.root / "backend" / "helpers.py").write_text(
            "def namedtuple(*args):\n    return {}\nValue = namedtuple('Value', [])\n",
            encoding="utf-8",
        )
        self.assertEqual(application_classes(self.root), {"backend.models.Entry", "backend.models.Response"})

    def test_frontend_runtime_classes_exclude_interfaces_declarations_and_comments(self) -> None:
        frontend = self.root / "frontend" / "src"
        frontend.mkdir(parents=True)
        (frontend / "api.ts").write_text(
            "/*\nexport class CommentOnly {}\n*/\n"
            "const example = `\nclass TextOnly {}\n`;\n"
            "// class AnotherComment {}\n"
            "interface Response {}\nexport type Status = number;\n"
            "export class ApiError extends Error {}\n",
            encoding="utf-8",
        )
        (frontend / "external.d.ts").write_text("export class External {}\n", encoding="utf-8")
        (frontend / "api.test.ts").write_text("class TestHelper {}\n", encoding="utf-8")
        self.assertEqual(application_classes(self.root), {
            "backend.models.Entry", "backend.models.Response", "frontend.src.api.ApiError",
        })
        with self.assertRaisesRegex(ValueError, "missing=.*frontend.src.api.ApiError"):
            check_class_coverage(self.root)

    def test_inventory_cannot_claim_a_nonexistent_declaration(self) -> None:
        (self.diagrams / "classes.puml").write_text("class Entry\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Response is not declared"):
            check_class_coverage(self.root)

    def test_obsolete_or_unsafe_inventory_is_rejected(self) -> None:
        self.inventory.write_text(json.dumps({"missing.Fake": ["classes"]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "obsolete"):
            check_class_coverage(self.root)
        self.inventory.write_text(json.dumps({
            "backend.models.Entry": ["../secret"],
            "backend.models.Response": ["classes"],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid diagram"):
            check_class_coverage(self.root)

    def test_plain_qualified_and_annotated_class_names_are_recognized(self) -> None:
        names = declared_classes(
            'class Entry <<DTO>> {\n}\nabstract class "backend.models.Response" as R\n'
            'class "App\\nDesktop UI" as App\n/\'\nclass CommentOnly\n\'/\n'
        )
        self.assertEqual(names, {"Entry", "Response", "App"})

    def test_image_checks_compare_pixels_not_container_encoding(self) -> None:
        rgb = Image.new("RGB", (3, 3), "white")
        rgba = Image.new("RGBA", (3, 3), (255, 255, 255, 255))
        transparent = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
        self.assertEqual(image_fingerprint(rgb), image_fingerprint(rgba))
        self.assertEqual(image_fingerprint(rgb), image_fingerprint(transparent))
        self.assertNotEqual(image_fingerprint(rgb), image_fingerprint(Image.new("RGB", (3, 3), "black")))

    def test_report_page_bounds_include_front_matter(self) -> None:
        for pages in (25, 26, 29, 30):
            check_report_page_count(pages)
        for pages in (0, 24, 31):
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "25-30 actual PDF pages"):
                check_report_page_count(pages)

    def test_signature_fields_and_signing_instructions_are_rejected(self) -> None:
        check_no_signature_fields("Author group: Name and Matricule. Contributions await review.")
        for text in ("Name | Matricule | Signature", "Group signatures are left blank."):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "signature fields"):
                check_no_signature_fields(text)

    def test_report_requires_both_current_automaton_images(self) -> None:
        lexer = Image.new("RGB", (8, 8), "white")
        parser = Image.new("RGB", (8, 8), "black")
        lexer.save(self.diagrams / "automaton-lexer.png")
        parser.save(self.diagrams / "automaton-parser.png")
        pdf_path = self.root / "docs" / "automata.pdf"
        lexer.save(pdf_path, format="PDF", save_all=True, append_images=[parser])
        reader = PdfReader(pdf_path, strict=True)
        source = (
            r"\automaton{automaton-lexer}{5cm}{DFA}"
            r"\automaton{automaton-parser}{5cm}{DPDA}"
        )
        self.assertEqual(check_report_automata(self.root / "docs", source, reader), 2)
        with self.assertRaisesRegex(ValueError, "lexer and parser automata"):
            check_report_automata(self.root / "docs", r"\automaton{automaton-lexer}", reader)
        Image.new("RGB", (8, 8), "blue").save(self.diagrams / "automaton-parser.png")
        with self.assertRaisesRegex(ValueError, "absent or stale"):
            check_report_automata(self.root / "docs", source, reader)

    def test_report_screenshots_require_current_registered_and_embedded_pixels(self) -> None:
        docs = self.root / "docs"
        screenshots = docs / "evidence" / "screenshots"
        screenshots.mkdir(parents=True)
        image_path = screenshots / "public-fixture.png"
        pdf_path = docs / "fixture.pdf"
        image = Image.new("RGB", (8, 8), "white")
        image.save(image_path)
        image.save(pdf_path, format="PDF")
        reader = PdfReader(pdf_path, strict=True)
        record = screenshots / "captures-20260927.json"
        record.write_text(json.dumps({"images": [{
            "file": image_path.name, "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        }]}), encoding="utf-8")
        source = r"\screen{public-fixture.png}{5cm}{Real capture}"
        self.assertEqual(check_report_screenshots(docs, source, reader), 1)
        with self.assertRaisesRegex(ValueError, "genuine application screenshots"):
            check_report_screenshots(docs, "", reader)
        Image.new("RGB", (8, 8), "black").save(image_path)
        with self.assertRaisesRegex(ValueError, "stale screenshot capture record"):
            check_report_screenshots(docs, source, reader)
        record.write_text(json.dumps({"images": [{
            "file": image_path.name, "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        }]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "absent or stale in the report"):
            check_report_screenshots(docs, source, reader)

    def test_sequence_calls_and_nested_activations_are_balanced(self) -> None:
        (self.diagrams / "sequence-fixture.puml").write_text(
            "@startuml\nactivate User\nUser -> API : request\nactivate API\n"
            "API -> API : self-call\nactivate API\nAPI --> API : result\ndeactivate API\n"
            "API --> User : result\ndeactivate API\ndeactivate User\n@enduml\n",
            encoding="utf-8",
        )
        self.assertEqual(check_sequence_activations(self.diagrams), 1)

    def test_missing_receiver_activation_fails_sequence_check(self) -> None:
        (self.diagrams / "sequence-fixture.puml").write_text(
            "activate User\nUser -> API : request\nAPI --> User : result\n", encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "receiver activation"):
            check_sequence_activations(self.diagrams)

    def test_mismatched_replies_and_open_activations_fail_sequence_check(self) -> None:
        sequence = self.diagrams / "sequence-fixture.puml"
        sequence.write_text(
            "activate User\nUser -> API : request\nactivate API\nAPI --> Wrong : reply\ndeactivate API\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "reply does not match"):
            check_sequence_activations(self.diagrams)
        sequence.write_text("activate User\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unfinished"):
            check_sequence_activations(self.diagrams)


if __name__ == "__main__":
    unittest.main()
