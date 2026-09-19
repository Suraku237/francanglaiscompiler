from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile

from .collection import CollectionError
from .gemini import GeminiService
from .import_models import MAX_FILE_BYTES, ImportPreview, SuggestionResponse, SuggestRequest
from .imports import preview_file, suggest_entries
from .uploads import multipart_form

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
    async with multipart_form(request, fields={"allow_cloud_processing"}) as form:
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


@router.post("/suggest", response_model=SuggestionResponse)
async def suggest(payload: SuggestRequest, request: Request) -> SuggestionResponse:
    service: GeminiService = request.app.state.gemini
    return await suggest_entries(payload, service)
