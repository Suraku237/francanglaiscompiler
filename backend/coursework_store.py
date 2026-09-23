import base64
import binascii
import io
import re
import sqlite3
from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from filelock import FileLock
from PIL import Image, UnidentifiedImageError
from PIL.PngImagePlugin import PngInfo

from compiler.parser.service import DEFAULT_GRAMMAR, analyze_grammar
from data_collector import dataset

from .analyzer_models import RecordedTest, StoredAnalyzerTest
from .collection import CollectionError
from .coursework_models import ProjectProfile, ScreenshotRequest
from .file_storage import atomic_write as _atomic_write

PROJECT_DIR = Path(__file__).resolve().parents[1] / "data_collector" / "coursework"
MAX_SCREENSHOTS = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class CourseworkStorage(Protocol):
    project: str

    def load_coursework(self) -> ProjectProfile | None: ...
    def save_coursework(self, profile: ProjectProfile) -> None: ...
    def list_coursework_screenshots(self) -> list[dict[str, str]]: ...
    def read_coursework_screenshot(self, image_id: str) -> bytes: ...
    def save_coursework_screenshot(self, image_id: str, name: str, content: bytes) -> None: ...
    def delete_coursework_screenshot(self, image_id: str) -> None: ...
    def load_analyzer_test(self, test_id: str) -> RecordedTest | None: ...
    def save_analyzer_test(self, record: RecordedTest) -> None: ...
    def iter_analyzer_tests(self) -> Iterator[RecordedTest]: ...


_storage: ContextVar[CourseworkStorage | None] = ContextVar("coursework_storage", default=None)


@contextmanager
def use_storage(storage: CourseworkStorage) -> Generator[None]:
    token = _storage.set(storage)
    try:
        yield
    finally:
        _storage.reset(token)


def screenshot_item(image_id: str, name: str) -> dict[str, str]:
    storage = _storage.get()
    url = f"/api/coursework/screenshots/{image_id}"
    if storage is not None:
        url += f"?project={storage.project}"
    return {"id": image_id, "name": name, "url": url}


def default_project() -> ProjectProfile:
    return ProjectProfile(group_members=["", "", ""], grammar=DEFAULT_GRAMMAR)


def load_project() -> ProjectProfile:
    storage = _storage.get()
    if storage is not None:
        return storage.load_coursework() or default_project()
    path = PROJECT_DIR / "project.json"
    if not path.exists():
        return default_project()
    return ProjectProfile.model_validate_json(path.read_bytes())


def save_project(profile: ProjectProfile) -> ProjectProfile:
    analyze_grammar(profile.grammar)
    storage = _storage.get()
    if storage is not None:
        storage.save_coursework(profile)
        return profile
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(PROJECT_DIR / "project.lock", timeout=10):
        _atomic_write(PROJECT_DIR / "project.json", profile.model_dump_json(indent=2).encode("utf-8"))
    return profile


@contextmanager
def _analyzer_database() -> Generator[sqlite3.Connection]:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with dataset.dataset_lock(), closing(sqlite3.connect(PROJECT_DIR / "analyzer-tests.sqlite3", timeout=10)) as db:
        db.row_factory = sqlite3.Row
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS analyzer_tests (id TEXT PRIMARY KEY,data TEXT NOT NULL)")
            yield db


def load_analyzer_test(test_id: str) -> RecordedTest | None:
    storage = _storage.get()
    if storage is not None:
        return storage.load_analyzer_test(test_id)
    with _analyzer_database() as db:
        row = db.execute("SELECT id,data FROM analyzer_tests WHERE id=?", (test_id,)).fetchone()
    return StoredAnalyzerTest.model_validate({**dict(row), "project_id": "default"}).data if row is not None else None


def save_analyzer_test(record: RecordedTest) -> None:
    storage = _storage.get()
    if storage is not None:
        storage.save_analyzer_test(record)
        return
    with _analyzer_database() as db:
        db.execute("INSERT INTO analyzer_tests VALUES (?,?)", (record.id, record.model_dump_json()))


def iter_analyzer_tests() -> Iterator[RecordedTest]:
    storage = _storage.get()
    if storage is not None:
        yield from storage.iter_analyzer_tests()
        return
    with _analyzer_database() as db:
        for row in db.execute("SELECT id,data FROM analyzer_tests ORDER BY rowid DESC"):
            yield StoredAnalyzerTest.model_validate({**dict(row), "project_id": "default"}).data


def list_screenshots() -> list[dict[str, str]]:
    storage = _storage.get()
    if storage is not None:
        return [screenshot_item(item["id"], item["name"]) for item in storage.list_coursework_screenshots()]
    directory = PROJECT_DIR / "screenshots"
    if not directory.exists():
        return []
    screenshots = []
    for index, path in enumerate(sorted(directory.glob("*.png"))):
        with Image.open(path) as image:
            title = image.info.get("Title", f"Analyzer evidence {index + 1}")
        screenshots.append(screenshot_item(path.stem, str(title)))
    return screenshots


def _check_image_id(image_id: str) -> None:
    if re.fullmatch(r"[a-f0-9]{32}", image_id) is None:
        raise CollectionError(404, "Screenshot not found.")


def _archive_screenshot_path(image_id: str) -> Path:
    _check_image_id(image_id)
    path = PROJECT_DIR / "screenshots" / f"{image_id}.png"
    if not path.is_file():
        raise CollectionError(404, "Screenshot not found.")
    return path


def screenshot_bytes(image_id: str) -> bytes:
    _check_image_id(image_id)
    storage = _storage.get()
    if storage is not None:
        return storage.read_coursework_screenshot(image_id)
    return _archive_screenshot_path(image_id).read_bytes()


def validate_stored_screenshot(content: bytes) -> None:
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Stored screenshots must be nonempty PNG files no larger than 2 MB.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG" or image.width * image.height > 12_000_000:
                raise ValueError("Invalid stored screenshot format or resolution.")
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The stored screenshot cannot be decoded.") from exc


def add_screenshot(request: ScreenshotRequest) -> dict[str, str]:
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=\r\n]+)", request.data_url)
    if match is None:
        raise CollectionError(422, "Upload a PNG or JPEG screenshot.")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise CollectionError(422, "The screenshot is not valid base64 data.") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise CollectionError(413, "Screenshots must be no larger than 2 MB.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("PNG", "JPEG"):
                raise CollectionError(422, "The file is not a PNG or JPEG image.")
            if image.width * image.height > 12_000_000:
                raise CollectionError(413, "Screenshot resolution must not exceed 12 megapixels.")
            image.load()
            clean = io.BytesIO()
            metadata = PngInfo()
            metadata.add_text("Title", request.name)
            image.convert("RGB").save(clean, format="PNG", pnginfo=metadata)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise CollectionError(422, "The screenshot could not be decoded.") from exc
    content = clean.getvalue()
    if len(content) > MAX_IMAGE_BYTES:
        raise CollectionError(413, "The normalized PNG exceeds 2 MB. Resize the screenshot before uploading.")
    image_id = uuid4().hex
    storage = _storage.get()
    if storage is not None:
        storage.save_coursework_screenshot(image_id, request.name, content)
        return screenshot_item(image_id, request.name)
    directory = PROJECT_DIR / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(PROJECT_DIR / "screenshots.lock", timeout=10):
        if len(list_screenshots()) >= MAX_SCREENSHOTS:
            raise CollectionError(422, f"Keep at most {MAX_SCREENSHOTS} screenshots; remove one before uploading.")
        _atomic_write(directory / f"{image_id}.png", content)
    return screenshot_item(image_id, request.name)


def delete_screenshot(image_id: str) -> None:
    _check_image_id(image_id)
    storage = _storage.get()
    if storage is not None:
        storage.delete_coursework_screenshot(image_id)
        return
    path = _archive_screenshot_path(image_id)
    with FileLock(PROJECT_DIR / "screenshots.lock", timeout=10):
        path.unlink()
