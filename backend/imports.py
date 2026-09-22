import csv
import io
import json
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from starlette.concurrency import run_in_threadpool

from .collection import CollectionError
from .import_models import (
    MAX_DRAFTS,
    MAX_EXTRACTED_TEXT,
    MAX_FILE_BYTES,
    MAX_PDF_PAGES,
    ImportPreview,
    ImportEntry,
)

MIME_TYPES = {
    ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv",
    ".json": "application/json", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac",
    ".webm": "audio/webm",
}
LOCAL_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".docx", ".pdf"}


def split_segments(text: str, limit: int = 4000) -> list[str]:
    segments = []
    while len(text) > limit:
        boundary = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        end = boundary + 1 if boundary >= limit // 2 else limit
        segments.append(text[:end])
        text = text[end:]
    if text:
        segments.append(text)
    return segments


def _check_text(text: str) -> str:
    if len(text) > MAX_EXTRACTED_TEXT:
        raise CollectionError(413, "The extracted text exceeds 40,000 characters. Split the document into smaller files.")
    if not text.strip():
        raise CollectionError(422, "No readable text was found. Supply a text document or a manual transcript.")
    return text


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CollectionError(422, "Save text, CSV and JSON files with UTF-8 encoding before importing.") from exc
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise CollectionError(422, "This file contains binary control characters, not readable UTF-8 text.")
    return _check_text(text)


def _drafts_from_rows(rows: list[object]) -> list[ImportEntry]:
    if len(rows) > MAX_DRAFTS:
        raise CollectionError(413, "Import at most 100 dataset rows at a time.")
    drafts = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise CollectionError(422, f"Dataset row {index} must contain a text string.")
        fields = {
            key: row[key] for key in (
                "text", "entry_type", "language", "french_gloss", "english_gloss", "lexical_category",
                "category", "source_location", "contributor", "notes",
            ) if key in row and row[key] != ""
        }
        # Imported approval flags never bypass the human review step.
        try:
            draft = ImportEntry.model_validate(fields)
        except ValidationError as exc:
            raise CollectionError(422, f"Dataset row {index} has invalid text or entry metadata.") from exc
        if not draft.text.strip():
            raise CollectionError(422, f"Dataset row {index} has empty text.")
        drafts.append(draft)
    return drafts


def _structured_drafts(text: str, extension: str) -> list[ImportEntry]:
    if extension == ".json":
        try:
            value = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise CollectionError(422, "This JSON file is invalid or too deeply nested.") from exc
        if isinstance(value, dict) and "entries" in value:
            if not isinstance(value["entries"], list):
                raise CollectionError(422, "The JSON entries field must be an array of records.")
            return _drafts_from_rows(value["entries"])
        if isinstance(value, list) and value and all(isinstance(row, dict) and "text" in row for row in value):
            return _drafts_from_rows(value)
    if extension == ".csv":
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            if reader.fieldnames and "text" in reader.fieldnames:
                if len(set(reader.fieldnames)) != len(reader.fieldnames):
                    raise CollectionError(422, "Dataset CSV column names must not be repeated.")
                rows = list(reader)
                if any(None in row or any(value is None for value in row.values()) for row in rows):
                    raise CollectionError(422, "The CSV has incomplete rows or extra cells. Check the header and quoting.")
                return _drafts_from_rows(list(rows))
            list(reader)
        except csv.Error as exc:
            raise CollectionError(422, "This CSV could not be parsed. Check its delimiters and quoting.") from exc
    return []


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(info.file_size for info in infos) > 32 * 1024 * 1024:
                raise CollectionError(413, "The DOCX expands beyond the safe import limit. Split or simplify it.")
            if "[Content_Types].xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                raise CollectionError(422, "This is not a supported Word DOCX document.")
            document = archive.getinfo("word/document.xml")
            if document.file_size > 4 * 1024 * 1024 or document.flag_bits & 1:
                raise CollectionError(413, "This DOCX is too large or encrypted. Export a smaller plain-text document.")
            xml = archive.read(document)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise CollectionError(422, "This DOCX file is corrupt, encrypted or uses unsupported compression.") from exc
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise CollectionError(422, "DOCX documents with XML entities are not supported.")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise CollectionError(422, "The DOCX document contains invalid XML.") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(namespace + "p"):
        fragments = []
        for node in paragraph.iter():
            if node.tag == namespace + "t":
                fragments.append(node.text or "")
            elif node.tag == namespace + "tab":
                fragments.append("\t")
            elif node.tag in (namespace + "br", namespace + "cr"):
                fragments.append("\n")
        paragraphs.append("".join(fragments))
    return _check_text("\n".join(paragraphs))


def _pdf_text(data: bytes) -> tuple[str, list[str], bool]:
    if not data.startswith(b"%PDF-"):
        raise CollectionError(422, "This file does not contain a valid PDF header.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise CollectionError(422, "Unlock this PDF locally before importing it.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise CollectionError(413, "Import PDFs of at most 40 pages. Split a longer document first.")
        pages = []
        empty_pages = 0
        length = 0
        for page in reader.pages:
            text = page.extract_text()
            empty_pages += not bool(text.strip())
            length += len(text) + (2 if pages else 0)
            if length > MAX_EXTRACTED_TEXT:
                raise CollectionError(413, "The PDF text exceeds 40,000 characters. Split the document first.")
            pages.append(text)
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, OSError) as exc:
        raise CollectionError(422, "This PDF could not be read safely. Export an unlocked, simpler PDF or a text file.") from exc
    warnings = []
    if empty_pages:
        warnings.append(f"{empty_pages} page(s) have no text layer. Local extraction does not read images or handwriting.")
    warnings.append("PDF text order may differ from the visual layout. Review columns, accents and line breaks.")
    return "\n\n".join(pages), warnings, bool(empty_pages)


def _local_preview(data: bytes, extension: str) -> tuple[str, list[ImportEntry], list[str], bool]:
    if extension == ".docx":
        return _docx_text(data), [], ["DOCX body text only; images, headers, footnotes and text boxes may need manual transcription."], False
    if extension == ".pdf":
        text, warnings, has_empty_pages = _pdf_text(data)
        return text, [], warnings, has_empty_pages
    text = _decode(data)
    drafts = _structured_drafts(text, extension) if extension in (".csv", ".json") else []
    return text, drafts, [], False


def validate_media(data: bytes, extension: str) -> None:
    valid = False
    if extension == ".mp3":
        valid = data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224)
    elif extension == ".wav":
        valid = data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    elif extension == ".ogg":
        valid = data.startswith(b"OggS")
    elif extension == ".flac":
        valid = data.startswith(b"fLaC")
    elif extension == ".m4a":
        valid = data[4:8] == b"ftyp"
    elif extension == ".webm":
        valid = data.startswith(b"\x1a\x45\xdf\xa3")
    if not valid:
        raise CollectionError(422, "The file contents do not match its supported extension. Export it in the correct format.")


async def preview_file(filename: str, data: bytes) -> ImportPreview:
    name = PurePosixPath(filename.replace("\\", "/")).name
    extension = PurePosixPath(name).suffix.lower()
    safe_name = name if len(name) <= 200 else name[:200 - len(extension)] + extension
    if extension not in LOCAL_EXTENSIONS:
        raise CollectionError(
            415, "Use TXT, MD, CSV, JSON, DOCX or a text-layer PDF. "
            "Images and recordings must be transcribed manually; attach raw audio in the collection."
        )
    if not data:
        raise CollectionError(422, "The selected file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise CollectionError(413, "The file exceeds 12 MB. Split or compress it before importing.")
    text, drafts, warnings, has_empty_pages = await run_in_threadpool(_local_preview, data, extension)
    if has_empty_pages and not text.strip():
        raise CollectionError(
            422, "This PDF has no readable text layer. Manually transcribe the source, "
            "then import the transcript as a text document. Automatic OCR is not available."
        )
    text = _check_text(text)
    return ImportPreview(
        filename=safe_name, format=extension[1:],
        text=text, segments=split_segments(text), drafts=drafts, warnings=warnings,
    )
