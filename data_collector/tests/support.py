import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from data_collector import dataset


def synthetic_entry(**changes):
    entry = dict.fromkeys(dataset.FIELDNAMES, "")
    entry.update(
        id="synthetic-entry", text="Synthetic desktop fixture",
        entry_type="Word", category="Other", contributor="Test fixture",
        timestamp="2000-01-01T00:00:00", language="unspecified",
        review_status="unreviewed",
    )
    entry.update(changes)
    return entry


class IsolatedDatasetTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(
            tempfile.TemporaryDirectory(prefix="mboa-desktop-test-")
        ))
        self.stack.enter_context(patch.object(dataset, "DATASET_PATH", str(self.directory / "dataset.csv")))
        self.stack.enter_context(patch.object(dataset, "AUDIO_DIR", str(self.directory / "audio")))
        self.stack.enter_context(patch.object(dataset, "_LOCKS", {}))
        dataset.ensure_dataset_file()
