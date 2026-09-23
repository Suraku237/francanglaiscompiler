from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class Ownership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str | None
    owner_name: str
    can_edit: bool


class OwnershipStore(Protocol):
    def ownership(self, kind: str, identifier: str) -> Ownership: ...
    def require_owner(self, kind: str, identifier: str) -> None: ...


_store: ContextVar[OwnershipStore | None] = ContextVar("record_ownership", default=None)


@contextmanager
def use_ownership(store: OwnershipStore) -> Generator[None, None, None]:
    token = _store.set(store)
    try:
        yield
    finally:
        _store.reset(token)


def record_ownership(kind: str, identifier: str) -> Ownership | None:
    store = _store.get()
    return store.ownership(kind, identifier) if store is not None else None


def require_owner(kind: str, identifier: str) -> None:
    store = _store.get()
    if store is not None:
        store.require_owner(kind, identifier)
