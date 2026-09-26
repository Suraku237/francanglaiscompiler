"""Seed only an already-started, isolated public browser fixture via storage helpers."""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4


def main() -> None:
    project = Path(__file__).resolve().parents[3]
    fixture_root = project / "frontend" / ".playwright"
    if len(sys.argv) != 2:
        raise ValueError("An explicit isolated browser data directory is required.")
    requested = Path(sys.argv[1])
    data = requested.resolve(strict=True)
    if (
        requested.is_symlink()
        or data.parent != fixture_root.resolve()
        or not data.name.startswith("mboa-live-")
        or not (data / "shared-workspace" / "workspace.sqlite3").is_file()
    ):
        raise ValueError("Seeding is restricted to a started frontend/.playwright/mboa-live-* fixture.")
    os.environ["MBOA_DATA_DIR"] = str(data)
    sys.path.insert(0, str(project))

    from backend import analyzer_history, coursework_store
    from backend.analyzer_models import AnalyzerTestRequest
    from backend.coursework_models import ProjectProfile
    from backend.file_storage import atomic_write
    from backend.readings_api import _save
    from backend.readings_models import ReadingUpload
    from backend.shared_workspace import SharedWorkspaceStore
    from backend.workspaces import use_workspace
    from compiler.parser.yaounde import GRAMMAR
    from compiler.tests.yaounde_cases import CORPUS_CASES
    from data_collector.tests.support import synthetic_entry

    seed = json.load(sys.stdin.buffer)
    store = SharedWorkspaceStore(data, "11111111-1111-4111-8111-111111111111", "Historical fixture curator", system=True)
    audio = (project / "frontend" / "tests" / "fixtures" / "imports" / "silence.wav").read_bytes()
    result = {"entry_ids": [], "reading_ids": [], "test_ids": []}
    with use_workspace(store):
        grammar = GRAMMAR if seed.get("corpus") == "yaounde" else seed.get("grammar")
        if grammar is not None:
            profile = ProjectProfile.model_validate({
                **coursework_store.load_project().model_dump(), "grammar": grammar,
            })
            coursework_store.save_project(profile)
        entries = seed.get("entries")
        if seed.get("corpus") == "yaounde":
            entries = [{"text": case.text, "entry_type": "Sentence"} for case in CORPUS_CASES]
        if entries is not None:
            records = []
            for fields in entries:
                values = dict(fields)
                with_audio = values.pop("audio", False)
                if with_audio:
                    values["audio_filename"] = f"{uuid4().hex}.wav"
                    atomic_write(store.audio_dir / values["audio_filename"], audio)
                record = synthetic_entry(**{
                    "id": str(uuid4()), "notes": "Isolated regression fixture, not fieldwork.", **values,
                })
                records.append(record)
                result["entry_ids"].append(record["id"])
            store.save_all(records)
        for reading in seed.get("readings", []):
            record = _save(ReadingUpload(**reading, share_consent=True), None, "fixture.wav", audio)
            result["reading_ids"].append(record.id)
        for test in seed.get("tests", []):
            record = analyzer_history.record_test(AnalyzerTestRequest(request_id=str(uuid4()), **test))
            result["test_ids"].append(record.id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
