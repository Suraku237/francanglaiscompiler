import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.check_documentation import application_classes, check_class_coverage, declared_classes, image_fingerprint


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


if __name__ == "__main__":
    unittest.main()
