import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from data_collector import dataset

from .analyzer_models import CanonicalUUID
from .audio_api import AUDIO_TYPES, _audio_extension
from .collection import CollectionError, storage_operation
from .file_storage import atomic_write
from .import_models import MAX_FILE_BYTES
from .readings_models import (
    ReadingConsent, ReadingLookup, ReadingRecord, ReadingSearch, ReadingUpload, ReadingView, StoredReading,
)
from .shared_workspace import SharedWorkspaceStore
from .uploads import multipart_form
from .workspaces import current_workspace, now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/readings", tags=["Recorded read-aloud"])
RECORDING_UPLOAD_SCHEMA = {"requestBody": {
    "required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file", "fields"], "additionalProperties": False,
        "properties": {
            "file": {"type": "string", "format": "binary", "description": "WAV, MP3, M4A, OGG, FLAC or WebM, up to 12 MB."},
            "fields": {"type": "string", "description": (
                'JSON with "share_consent": true. New readings also require "text" and "language" ("fr" or "en").'
            )},
        },
    }}},
}}


def _store() -> SharedWorkspaceStore:
    store = current_workspace()
    if not isinstance(store, SharedWorkspaceStore):
        raise CollectionError(403, "Recorded read-aloud requires a signed-in shared workspace.")
    return store


def _find(store: SharedWorkspaceStore, identifier: str) -> ReadingRecord:
    with store.connection() as db:
        row = db.execute("SELECT * FROM readings WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise CollectionError(404, "This recorded reading no longer exists.")
    return StoredReading.model_validate(dict(row)).data


def _view(store: SharedWorkspaceStore, record: ReadingRecord) -> ReadingView:
    return ReadingView(
        **record.model_dump(), ownership=store.ownership("reading", record.id),
        audio_url=f"/api/readings/{record.id}/audio",
    )


@router.post("/lookup")
def find_reading(payload: ReadingLookup) -> ReadingSearch:
    def operation() -> ReadingSearch:
        store = _store()
        with store.lock(), store.connection() as db:
            row = db.execute("SELECT * FROM readings WHERE key=?", (payload.lookup_key(),)).fetchone()
            return ReadingSearch(reading=_view(store, StoredReading.model_validate(dict(row)).data) if row else None)
    return storage_operation(operation)


def _save(payload: ReadingUpload | ReadingConsent, identifier: str | None, filename: str, content: bytes) -> ReadingView:
    store = _store()
    path: Path | None = None
    committed = False
    with store.lock():
        previous = _find(store, identifier) if identifier is not None else None
        if previous is not None:
            store.require_owner("reading", previous.id)
        elif isinstance(payload, ReadingUpload):
            with store.connection() as db:
                if db.execute("SELECT 1 FROM readings WHERE key=?", (payload.lookup_key(),)).fetchone():
                    raise CollectionError(409, "A reading already exists for this text and language. Refresh to view it.")
        else:
            raise ValueError("A new reading requires text and language.")
        extension = _audio_extension(filename, content)
        dataset.check_audio_capacity(len(content))
        path = store.audio_dir / f"{uuid4().hex}{extension}"
        try:
            atomic_write(path, content)
            stamp = now()
            if previous is not None:
                record = previous.model_copy(update={"audio_filename": path.name, "updated_at": stamp})
            elif isinstance(payload, ReadingUpload):
                record = ReadingRecord(
                    id=str(uuid4()), text=payload.text, language=payload.language,
                    audio_filename=path.name, created_at=stamp, updated_at=stamp,
                )
            else:
                raise ValueError("Missing reading creation fields.")
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                store.authorize_write(db, "reading", record.id, new=previous is None)
                if previous is None:
                    db.execute("INSERT INTO readings VALUES (?,?,?)", (record.id, record.lookup_key(), record.model_dump_json()))
                else:
                    db.execute("UPDATE readings SET data=? WHERE id=?", (record.model_dump_json(), record.id))
                store.bump(db)
            committed = True
            return _view(store, record)
        finally:
            if path is not None and not committed:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove an uncommitted read-aloud recording.")


async def _upload(request: Request, identifier: str | None = None) -> ReadingView:
    async with multipart_form(request, fields={"fields"}, max_field_bytes=65536) as form:
        raw = form.get("fields")
        file = form.get("file")
        if not isinstance(raw, str) or not isinstance(file, UploadFile):
            raise CollectionError(422, "Supply an audio file and the recording fields.")
        try:
            payload = ReadingUpload.model_validate_json(raw) if identifier is None else ReadingConsent.model_validate_json(raw)
        except ValidationError as exc:
            raise CollectionError(422, f"Invalid recording fields: {exc.errors()[0]['msg']}") from exc
        content = await file.read(MAX_FILE_BYTES + 1)
        return await run_in_threadpool(
            storage_operation, lambda: _save(payload, identifier, file.filename or "", content),
        )


@router.post("/audio", status_code=201, openapi_extra=RECORDING_UPLOAD_SCHEMA)
async def create_reading(request: Request) -> ReadingView:
    return await _upload(request)


@router.patch("/{reading_id}/audio", openapi_extra=RECORDING_UPLOAD_SCHEMA)
async def replace_reading(reading_id: CanonicalUUID, request: Request) -> ReadingView:
    return await _upload(request, reading_id)


@router.get("/{reading_id}/audio")
def play_reading(reading_id: CanonicalUUID) -> FileResponse:
    def operation() -> FileResponse:
        store = _store()
        with store.lock():
            record = _find(store, reading_id)
            path = store.audio_dir / record.audio_filename
            if path.is_symlink() or not path.is_file() or path.resolve().parent != store.audio_dir.resolve():
                raise CollectionError(404, "The recorded audio is missing or outside its storage folder.")
            return FileResponse(
                path, media_type=AUDIO_TYPES[path.suffix.lower()], filename=record.audio_filename,
                content_disposition_type="inline",
                headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
            )
    return storage_operation(operation)


@router.delete("/{reading_id}", status_code=204)
def remove_reading(reading_id: CanonicalUUID) -> Response:
    def operation() -> None:
        store = _store()
        with store.lock(), store.connection() as db:
            _find(store, reading_id)
            store.authorize_write(db, "reading", reading_id)
            db.execute("DELETE FROM readings WHERE id=?", (reading_id,))
            store.bump(db)
    storage_operation(operation)
    return Response(status_code=204)
