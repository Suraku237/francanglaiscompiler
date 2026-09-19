import io
import logging
import wave
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from data_collector import dataset

from .collection import CollectionError, create_entry, edit_entry, storage_operation
from .file_storage import atomic_write
from .import_models import MAX_FILE_BYTES
from .imports import MIME_TYPES, validate_media
from .schemas import DatasetEntry, EntryCreate, EntryPatch
from .uploads import multipart_form

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dataset", tags=["Local collection audio"])
AUDIO_TYPES = {
    extension: MIME_TYPES[extension]
    for extension in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm")
}
AUDIO_TYPES[".webm"] = "audio/webm"


def _upload_schema(*, edit: bool) -> dict:
    properties = {
        "file": {"type": "string", "format": "binary"},
        "fields": {"type": "string", "description": (
            "JSON entry creation or changed-field values. Include review_status for an audio-only edit."
        )},
    }
    if edit:
        properties["remove_audio"] = {"type": "string", "enum": ["true", "false"]}
    return {
        "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "properties": properties,
            "required": ["fields"] if edit else ["fields", "file"],
            "additionalProperties": False,
        }}}},
    }


def _audio_extension(filename: str, data: bytes) -> str:
    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if extension not in AUDIO_TYPES:
        raise CollectionError(415, "Attach WAV, MP3, M4A, OGG, FLAC or WebM audio.")
    if not data:
        raise CollectionError(422, "The audio file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise CollectionError(413, "Audio attachments must not exceed 12 MB.")
    validate_media(data, extension)
    if extension == ".wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as recording:
                frames = recording.getnframes()
                if frames == 0 or len(recording.readframes(frames)) != (
                    frames * recording.getnchannels() * recording.getsampwidth()
                ):
                    raise CollectionError(422, "The WAV recording has no samples or is incomplete.")
        except (wave.Error, EOFError) as exc:
            raise CollectionError(422, "The WAV file is invalid. Export a complete PCM WAV recording.") from exc
    return extension


def _store_audio_entry(
    fields: EntryCreate | EntryPatch, entry_id: str | None,
    filename: str = "", content: bytes | None = None,
) -> DatasetEntry:
    path = None
    committed = False
    try:
        if content is not None:
            extension = _audio_extension(filename, content)
            directory = Path(dataset.AUDIO_DIR)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid4().hex}{extension}"
            atomic_write(path, content)
        attachment = path.name if path is not None else ""
        if isinstance(fields, EntryCreate) and entry_id is None:
            result = create_entry(fields, audio_filename=attachment)
        elif isinstance(fields, EntryPatch) and entry_id is not None:
            result = edit_entry(entry_id, fields, audio_filename=attachment)
        else:
            raise ValueError("Audio mutation fields do not match the operation.")
        committed = True
        return result
    finally:
        if path is not None and not committed:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove an uncommitted collection audio attachment.")


def _save_with_audio(
    fields: EntryCreate | EntryPatch, entry_id: str | None,
    filename: str = "", content: bytes | None = None,
) -> DatasetEntry:
    def operation() -> DatasetEntry:
        with dataset.dataset_lock():
            return _store_audio_entry(fields, entry_id, filename, content)
    return storage_operation(operation)


@router.post("/audio", response_model=DatasetEntry, status_code=201, openapi_extra=_upload_schema(edit=False))
async def create_with_audio(request: Request) -> DatasetEntry:
    async with multipart_form(request, fields={"fields"}, max_field_bytes=65536) as form:
        file = form.get("file")
        raw_fields = form.get("fields")
        if not isinstance(file, UploadFile) or not isinstance(raw_fields, str):
            raise CollectionError(422, "Supply an audio file and JSON entry fields.")
        try:
            fields = EntryCreate.model_validate_json(raw_fields)
        except ValidationError as exc:
            raise CollectionError(422, f"Invalid entry fields: {exc.errors()[0]['msg']}") from exc
        content = await file.read(MAX_FILE_BYTES + 1)
        return await run_in_threadpool(_save_with_audio, fields, None, file.filename or "", content)


@router.patch("/{entry_id}/audio", response_model=DatasetEntry, openapi_extra=_upload_schema(edit=True))
async def edit_with_audio(entry_id: str, request: Request) -> DatasetEntry:
    async with multipart_form(
        request, fields={"fields", "remove_audio"}, max_field_bytes=65536, file_required=False,
    ) as form:
        file = form.get("file")
        raw_fields = form.get("fields")
        remove = form.get("remove_audio", "false")
        if not isinstance(raw_fields, str) or remove not in ("true", "false"):
            raise CollectionError(422, "Supply JSON entry fields and a true/false remove_audio value.")
        if (remove == "true") == isinstance(file, UploadFile):
            raise CollectionError(422, "Choose either a replacement file or removal of the attachment.")
        try:
            fields = EntryPatch.model_validate_json(raw_fields)
        except ValidationError as exc:
            raise CollectionError(422, f"Invalid changed fields: {exc.errors()[0]['msg']}") from exc
        if isinstance(file, UploadFile):
            content = await file.read(MAX_FILE_BYTES + 1)
            return await run_in_threadpool(_save_with_audio, fields, entry_id, file.filename or "", content)
        return await run_in_threadpool(_save_with_audio, fields, entry_id)


def _audio_response(entry_id: str) -> FileResponse:
    entry = next((entry for entry in dataset.load_all() if entry["id"] == entry_id), None)
    if entry is None:
        raise CollectionError(404, "This collection entry no longer exists.")
    filename = entry["audio_filename"]
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        raise CollectionError(404, "No readable audio is attached to this entry.")
    directory = Path(dataset.AUDIO_DIR).resolve()
    path = (directory / filename).resolve()
    if path.parent != directory or not path.is_file():
        raise CollectionError(404, "The attached audio file is missing or outside the audio folder.")
    media_type = AUDIO_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise CollectionError(415, "This attachment cannot be played in the web app. Use the desktop player.")
    return FileResponse(
        path, media_type=media_type, filename=filename, content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{entry_id}/audio")
def read_audio(entry_id: str) -> FileResponse:
    return storage_operation(lambda: _audio_response(entry_id))
