from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .collection import CollectionError
from .import_models import MAX_FILE_BYTES


@asynccontextmanager
async def multipart_form(
    request: Request, *, fields: set[str], max_field_bytes: int = 64,
    file_required: bool = True, max_file_bytes: int = MAX_FILE_BYTES,
) -> AsyncIterator[FormData]:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError as exc:
            raise CollectionError(400, "Invalid upload size.") from exc
        if size < 0 or size > max_file_bytes + 65536:
            raise CollectionError(413, f"The upload exceeds {max_file_bytes // (1024 * 1024)} MB. Split or compress the file.")
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise CollectionError(422, "Choose a file using a multipart upload.")

    async def bounded_stream() -> AsyncIterator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_file_bytes + 65536:
                raise MultiPartException(f"Upload exceeds {max_file_bytes // (1024 * 1024)} MB.")
            yield chunk

    try:
        form = await MultiPartParser(
            request.headers, bounded_stream(), max_files=1, max_fields=len(fields),
            max_part_size=max_field_bytes,
        ).parse()
    except MultiPartException as exc:
        status = 413 if exc.message.startswith("Upload exceeds ") else 400
        raise CollectionError(status, exc.message) from exc
    except MultipartParseError as exc:
        raise CollectionError(400, "Malformed multipart upload. Select the file and try again.") from exc
    try:
        file = form.get("file")
        if (file_required or file is not None) and not isinstance(file, UploadFile):
            raise CollectionError(422, "Choose one file to upload.")
        if set(form.keys()) - {"file", *fields} or any(len(form.getlist(key)) != 1 for key in form):
            raise CollectionError(422, "Supply one file and the supported fields only, without duplicates.")
        yield form
    finally:
        await form.close()
