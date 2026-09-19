import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.check_documentation import (
    application_classes, check_class_coverage, check_sequence_activations, declared_classes, image_fingerprint,
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
