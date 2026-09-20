"""Synthetic import fixtures; run this module to regenerate the browser documents."""

import io
import wave
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


def pdf_bytes(
    text: bool = True, pages: int = 1, encrypted: bool = False, *,
    page_texts: list[str] | None = None,
) -> bytes:
    writer = PdfWriter()
    for content in page_texts if page_texts is not None else ["Cameroon language sample."] * pages:
        page = writer.add_blank_page(595, 842)
        if text:
            escaped = content.encode("ascii").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 72 720 Td (" + escaped + b") Tj ET")
            page[NameObject("/Contents")] = stream
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }),
                }),
            })
    if encrypted:
        writer.encrypt("local-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx_bytes(xml: str | None = None) -> bytes:
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>'
        ),
        "word/document.xml": xml or (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Bonjour</w:t><w:tab/><w:t>Cameroon</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Second line.</w:t></w:r></w:p></w:body></w:document>'
        ),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in parts.items():
            member = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, content.encode("utf-8"))
    return output.getvalue()


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "imports"
    destination.mkdir(parents=True, exist_ok=True)
    boundary = "A" * 39_996 + "END!"
    documents = {
        "silence.wav": wav_bytes(),
        "business.pdf": pdf_bytes(page_texts=["Order TEST-1042 contains 3 items. Do not send before Tuesday."]),
        "at-limit.pdf": pdf_bytes(page_texts=[boundary]),
        "over-limit.pdf": pdf_bytes(page_texts=[boundary + "!"]),
        "no-text-layer.pdf": pdf_bytes(text=False),
        "business.docx": docx_bytes(
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Commande TEST-1042.</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Exp\u00e9dition</w:t><w:tab/><w:t>mardi.</w:t>'
            '<w:br/><w:t>3 articles.</w:t></w:r></w:p></w:body></w:document>'
        ),
    }
    for filename, data in documents.items():
        (destination / filename).write_bytes(data)
        print(f"Generated synthetic fixture: {filename}")
    Image.new("RGB", (8, 8), "white").save(destination / "image.png")
    print("Generated synthetic fixture: image.png")
