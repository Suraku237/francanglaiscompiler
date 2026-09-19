import csv
import unittest
from pathlib import Path
from unittest.mock import patch

from data_collector import dataset
from data_collector.tests.support import IsolatedDatasetTest, synthetic_entry


class DatasetMutationTests(IsolatedDatasetTest):
    def test_update_missing_entry_fails_without_rewriting_csv(self):
        dataset.append_entry(synthetic_entry())
        before = Path(dataset.DATASET_PATH).read_bytes()
        with patch.object(dataset, "_write_entries", wraps=dataset._write_entries) as write:
            with self.assertRaises(dataset.EntryNotFoundError):
                dataset.update_entry("deleted-elsewhere", {"text": "Not stored"})
            write.assert_not_called()
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)

    def test_delete_missing_entry_fails_without_rewriting_csv(self):
        dataset.append_entry(synthetic_entry())
        with patch.object(dataset, "_write_entries", wraps=dataset._write_entries) as write:
            with self.assertRaises(dataset.EntryNotFoundError):
                dataset.delete_entry("deleted-elsewhere")
            write.assert_not_called()

    def test_evidence_edit_invalidates_review_and_preserves_provenance(self):
        original = synthetic_entry(
            review_status="approved", language="pidgin", lexical_category="NOUN",
            audio_filename="original.wav",
        )
        dataset.append_entry(original)
        dataset.update_entry(original["id"], {"notes": "A revised synthetic note"})
        updated = dataset.load_all()[0]
        self.assertEqual(updated["review_status"], "unreviewed")
        for key in ("id", "timestamp", "contributor", "audio_filename", "language", "lexical_category"):
            self.assertEqual(updated[key], original[key])

    def test_unchanged_evidence_preserves_approval(self):
        original = synthetic_entry(review_status="approved")
        dataset.append_entry(original)
        dataset.update_entry(original["id"], {"text": original["text"]})
        self.assertEqual(dataset.load_all()[0]["review_status"], "approved")

    def test_explicit_reapproval_accepts_changed_evidence(self):
        dataset.append_entry(synthetic_entry(review_status="approved"))
        dataset.update_entry("synthetic-entry", {"language": "pidgin", "review_status": "approved"})
        entry = dataset.load_all()[0]
        self.assertEqual(entry["language"], "pidgin")
        self.assertEqual(entry["review_status"], "approved")

    def test_failed_atomic_write_keeps_original_csv_and_removes_staging_file(self):
        dataset.append_entry(synthetic_entry())
        before = Path(dataset.DATASET_PATH).read_bytes()
        with patch.object(dataset.os, "replace", side_effect=PermissionError("CSV locked")):
            with self.assertRaises(PermissionError):
                dataset.update_entry("synthetic-entry", {"text": "not committed"})
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assertEqual(list(self.directory.glob(".dataset-*.tmp")), [])

    def test_legacy_headers_receive_only_metadata_defaults(self):
        for header in (dataset.LEGACY_FIELDNAMES, dataset.PRE_REVIEW_FIELDNAMES):
            with self.subTest(header=header):
                original = synthetic_entry(text="  preserve raw speech  ", entry_type="", category="")
                with open(dataset.DATASET_PATH, "w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=header)
                    writer.writeheader()
                    writer.writerow({key: original[key] for key in header})
                loaded = dataset.load_all()[0]
                self.assertEqual(loaded["language"], "unspecified")
                self.assertEqual(loaded["review_status"], "unreviewed")
                self.assertEqual(loaded["lexical_category"], "")
                dataset.update_entry(original["id"], {"language": "mixed"})
                updated = dataset.load_all()[0]
                for key in header:
                    self.assertEqual(updated[key], original[key])

    def test_duplicates_remain_advisory_and_are_language_specific(self):
        dataset.append_entry(synthetic_entry(text="Ma\u2019a  TEST", language="pidgin"))
        self.assertTrue(dataset.text_exists(" ma'a test ", language="pidgin"))
        self.assertFalse(dataset.text_exists("ma'a test", language="francanglais"))
        self.assertFalse(dataset.text_exists("ma'a test", exclude_id="synthetic-entry", language="pidgin"))
        dataset.append_entry(synthetic_entry(id="duplicate", text="ma'a test", language="pidgin"))
        self.assertEqual(dataset.total_count(), 2)

    def test_successful_delete_preserves_other_rows(self):
        first, second = synthetic_entry(), synthetic_entry(id="kept")
        dataset.save_all([first, second])
        dataset.delete_entry(first["id"])
        self.assertEqual(dataset.load_all(), [second])


if __name__ == "__main__":
    unittest.main()
