import base64
import binascii
import io
import re
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
from PIL import Image, UnidentifiedImageError
from PIL.PngImagePlugin import PngInfo

from compiler.parser.service import DEFAULT_GRAMMAR, analyze_grammar

from .collection import CollectionError
from .coursework_models import ProjectProfile, ScreenshotRequest
from .file_storage import atomic_write as _atomic_write

PROJECT_DIR = Path(__file__).resolve().parents[1] / "data_collector" / "coursework"
MAX_SCREENSHOTS = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def default_project() -> ProjectProfile:
    return ProjectProfile(group_members=["", "", ""], grammar=DEFAULT_GRAMMAR)


def load_project() -> ProjectProfile:
    path = PROJECT_DIR / "project.json"
    if not path.exists():
        return default_project()
    return ProjectProfile.model_validate_json(path.read_bytes())


def save_project(profile: ProjectProfile) -> ProjectProfile:
    analyze_grammar(profile.grammar)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(PROJECT_DIR / "project.lock", timeout=10):
        _atomic_write(PROJECT_DIR / "project.json", profile.model_dump_json(indent=2).encode("utf-8"))
    return profile


def list_screenshots() -> list[dict[str, str]]:
    directory = PROJECT_DIR / "screenshots"
    if not directory.exists():
        return []
    screenshots = []
    for index, path in enumerate(sorted(directory.glob("*.png"))):
        with Image.open(path) as image:
            title = image.info.get("Title", f"Analyzer evidence {index + 1}")
        screenshots.append({
            "id": path.stem, "name": str(title), "url": f"/api/coursework/screenshots/{path.stem}",
        })
    return screenshots


def screenshot_path(image_id: str) -> Path:
    if re.fullmatch(r"[a-f0-9]{32}", image_id) is None:
        raise CollectionError(404, "Screenshot not found.")
    path = PROJECT_DIR / "screenshots" / f"{image_id}.png"
    if not path.is_file():
        raise CollectionError(404, "Screenshot not found.")
    return path


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
    directory = PROJECT_DIR / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(PROJECT_DIR / "screenshots.lock", timeout=10):
        if len(list_screenshots()) >= MAX_SCREENSHOTS:
            raise CollectionError(422, f"Keep at most {MAX_SCREENSHOTS} screenshots; remove one before uploading.")
        image_id = uuid4().hex
        _atomic_write(directory / f"{image_id}.png", clean.getvalue())
    return {"id": image_id, "name": request.name, "url": f"/api/coursework/screenshots/{image_id}"}


def delete_screenshot(image_id: str) -> None:
    path = screenshot_path(image_id)
    with FileLock(PROJECT_DIR / "screenshots.lock", timeout=10):
        path.unlink()
