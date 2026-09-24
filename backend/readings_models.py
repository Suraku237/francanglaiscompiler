from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import Json, StringConstraints, field_validator, model_validator

from compiler.lexer.vocabulary import normalize_text

from .analyzer_models import CanonicalUUID, SnapshotModel, Timestamp
from .ownership import Ownership


class ReadingLookup(SnapshotModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r"\S")]
    language: Literal["fr", "en"]

    def lookup_key(self) -> str:
        normalized = " ".join(normalize_text(self.text).split())
        return sha256(f"{self.language}\0{normalized}".encode("utf-8")).hexdigest()


class ReadingConsent(SnapshotModel):
    share_consent: Literal[True]

    @field_validator("share_consent", mode="before")
    @classmethod
    def explicit_consent(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Confirm permission to share this voice recording.")
        return True


class ReadingUpload(ReadingLookup, ReadingConsent):
    pass


class ReadingRecord(ReadingLookup):
    id: CanonicalUUID
    audio_filename: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}\.(wav|mp3|m4a|ogg|flac|webm)$")]
    created_at: Timestamp
    updated_at: Timestamp


class ReadingView(ReadingRecord):
    ownership: Ownership
    audio_url: str


class ReadingSearch(SnapshotModel):
    reading: ReadingView | None


class StoredReading(SnapshotModel):
    id: CanonicalUUID
    key: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    data: Json[ReadingRecord]

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        if self.id != self.data.id or self.key != self.data.lookup_key():
            raise ValueError("The recording identity does not match its text and language.")
        return self
