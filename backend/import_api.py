from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .collection import CollectionError
from .gemini import GeminiService
from .import_models import MAX_FILE_BYTES, ImportPreview, SuggestionResponse, SuggestRequest
from .imports import preview_file, suggest_entries

router = APIRouter(prefix="/api/imports", tags=["Reviewed language imports"])


@router.post("/preview", response_model=ImportPreview, openapi_extra={
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "format": "binary", "description": "One supported file, at most 12 MB."},
                "allow_cloud_processing": {
                    "type": "string", "enum": ["true", "false"], "default": "false",
                    "description": "Explicit consent to send this file to Gemini when transcription or OCR is needed.",
                },
            },
            "required": ["file"],
            "additionalProperties": False,
        }}},
    },
})
async def preview(request: Request) -> ImportPreview:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError as exc:
            raise CollectionError(400, "Invalid upload size.") from exc
        if size < 0 or size > MAX_FILE_BYTES + 65536:
            raise CollectionError(413, "The upload exceeds 12 MB. Split or compress the file.")
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise CollectionError(422, "Choose one file to preview using a multipart upload.")

    async def bounded_stream() -> AsyncGenerator[bytes, None]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_FILE_BYTES + 65536:
                raise MultiPartException("Upload exceeds 12 MB.")
            yield chunk

    try:
        form = await MultiPartParser(
            request.headers, bounded_stream(), max_files=1, max_fields=1, max_part_size=64,
        ).parse()
    except MultiPartException as exc:
        status = 413 if exc.message == "Upload exceeds 12 MB." else 400
        raise CollectionError(status, exc.message) from exc
    except MultipartParseError as exc:
        raise CollectionError(400, "Malformed multipart upload. Select the file and try again.") from exc
    try:
        file = form.get("file")
        consent = form.get("allow_cloud_processing", "false")
        if not isinstance(file, UploadFile):
            raise CollectionError(422, "Choose one file to preview.")
        if len(form.getlist("file")) != 1 or set(form.keys()) - {"file", "allow_cloud_processing"}:
            raise CollectionError(422, "Supply one file and the cloud-processing consent field only.")
        if consent not in ("true", "false") or len(form.getlist("allow_cloud_processing")) > 1:
            raise CollectionError(422, "Cloud-processing consent must be true or false.")
        data = await file.read(MAX_FILE_BYTES + 1)
        service: GeminiService = request.app.state.gemini
        return await preview_file(file.filename or "", data, consent == "true", service)
    finally:
        await form.close()


@router.post("/suggest", response_model=SuggestionResponse)
async def suggest(payload: SuggestRequest, request: Request) -> SuggestionResponse:
    service: GeminiService = request.app.state.gemini
    return await suggest_entries(payload, service)
