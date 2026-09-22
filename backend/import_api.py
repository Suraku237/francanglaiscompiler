from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile

from .collection import CollectionError
from .import_models import MAX_FILE_BYTES, ImportPreview
from .imports import preview_file
from .uploads import multipart_form

router = APIRouter(prefix="/api/imports", tags=["Local text imports"])


@router.post("/preview", response_model=ImportPreview, openapi_extra={
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "format": "binary", "description": "One supported file, at most 12 MB."},
            },
            "required": ["file"],
            "additionalProperties": False,
        }}},
    },
})
async def preview(request: Request) -> ImportPreview:
    async with multipart_form(request, fields=set()) as form:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise CollectionError(422, "Choose one file to preview.")
        if len(form.getlist("file")) != 1 or set(form.keys()) != {"file"}:
            raise CollectionError(422, "Supply one local text document only.")
        data = await file.read(MAX_FILE_BYTES + 1)
        return await preview_file(file.filename or "", data)
