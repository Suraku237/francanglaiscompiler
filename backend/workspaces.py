import base64
import json
import re
import sqlite3
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, Query, Request
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from compiler.parser.service import analyze_grammar
from compiler.parser.grammar import read_grammar
from data_collector import dataset
from . import coursework_store
from .auth import UserIdentity, private_directory
from .analyzer_models import RecordedTest, StoredAnalyzerTest
from .collection import CollectionError, storage_operation
from .coursework_models import ProjectProfile
from .schemas import DatasetEntry, EntryCreate, TranslationLanguage

MAX_ENTRIES = 10000
MAX_HISTORY = 500
MAX_REVISIONS = 20000
MAX_AUDIO_BYTES = 128 * 1024 * 1024
_workspace: ContextVar["WorkspaceStore | None"] = ContextVar("mboa_workspace", default=None)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_id(value: str, *, default: bool = False) -> str:
    if default and value == "default":
        return value
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise CollectionError(422, "Invalid workspace record identifier.") from exc
    return value


def media_name(value: str) -> str:
    if value and not re.fullmatch(r"[0-9a-f]{32}\.(wav|mp3|m4a|ogg|flac|webm)", value):
        raise CollectionError(422, "Invalid workspace audio filename.")
    return value


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(WorkspaceInput):
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")


class SavedTranslation(WorkspaceInput):
    source_text: str = Field(min_length=1, max_length=4000)
    source_language: TranslationLanguage
    target_language: TranslationLanguage
    translation: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(default="", max_length=4000)
    note: str = Field(default="", max_length=2000)


class SavedMessage(WorkspaceInput):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class SavedConversation(WorkspaceInput):
    messages: list[SavedMessage] = Field(min_length=1, max_length=100)


class HistoryInput(WorkspaceInput):
    kind: Literal["translation", "conversation"]
    title: str = Field(min_length=1, max_length=100, pattern=r"\S")
    content: SavedTranslation | SavedConversation

    def document(self) -> dict:
        if ((self.kind == "translation" and not isinstance(self.content, SavedTranslation)) or
                (self.kind == "conversation" and not isinstance(self.content, SavedConversation))):
            raise CollectionError(422, "The saved content does not match its type.")
        return self.model_dump()


class RestoreRevision(WorkspaceInput):
    expected_version: int = Field(ge=0)


class WorkspaceStore:
    def __init__(self, data_dir: Path, user_id: str, project: str = "default"):
        valid_id(user_id)
        valid_id(project, default=True)
        self.user_id = user_id
        self.root = self.storage_root(data_dir, user_id)
        private_directory(self.root)
        self.audio_dir = self.root / "audio"
        private_directory(self.audio_dir)
        self.path = self.root / "workspace.sqlite3"
        if self.path.is_symlink():
            raise CollectionError(503, "The workspace storage path is invalid.")
        self.project = project
        self._lock = FileLock(str(self.root / "workspace.lock"), timeout=10)
        with self.lock(), self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('version','0');
                CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),entry_id TEXT NOT NULL,
                    action TEXT NOT NULL,timestamp TEXT NOT NULL,before_data TEXT,after_data TEXT
                );
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),
                    kind TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS coursework (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id),data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS screenshots (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),
                    name TEXT NOT NULL,content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analyzer_tests (
                    id TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id),data TEXT NOT NULL,
                    PRIMARY KEY (project_id,id)
                );
            """)
            db.execute("INSERT OR IGNORE INTO projects VALUES ('default','General',?)", (now(),))
            if db.execute("SELECT id FROM projects WHERE id=?", (project,)).fetchone() is None:
                raise CollectionError(404, "This project does not exist in your workspace.")

    def storage_root(self, data_dir: Path, user_id: str) -> Path:
        return data_dir / "workspaces" / user_id

    def authorize_write(
        self, db: sqlite3.Connection, kind: str, identifier: str, *, new: bool = False,
    ) -> None:
        # Private stores are account-scoped; shared stores override this record-level guard.
        pass

    def authorize_import(self, document: dict) -> None:
        pass

    def lock(self) -> FileLock:
        return self._lock

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    @property
    def version(self) -> int:
        with self.connection() as db:
            return int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])

    @staticmethod
    def bump(db: sqlite3.Connection):
        db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='version'")

    def load_all(self) -> list[dict[str, str]]:
        with self.lock(), self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM entries WHERE project_id=? ORDER BY rowid", (self.project,),
            )]

    def ensure(self) -> None:
        private_directory(self.audio_dir)

    def save_all(self, entries: list[dict[str, str]], *, action: str | None = None) -> None:
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = {row["id"]: json.loads(row["data"]) for row in db.execute(
                "SELECT id,data FROM entries WHERE project_id=?", (self.project,),
            )}
            incoming = {entry["id"]: entry for entry in entries}
            if len(incoming) != len(entries):
                raise CollectionError(422, "Entry identifiers must be unique.")
            total = db.execute("SELECT count(*) FROM entries").fetchone()[0] - len(previous) + len(entries)
            if total > MAX_ENTRIES:
                raise CollectionError(409, "The workspace limit is 10,000 terminology entries.")
            changes = [
                (entry_id, previous.get(entry_id), incoming.get(entry_id))
                for entry_id in dict.fromkeys([*previous, *incoming]) if previous.get(entry_id) != incoming.get(entry_id)
            ]
            count = db.execute("SELECT count(*) FROM revisions").fetchone()[0]
            if count + len(changes) > MAX_REVISIONS:
                raise CollectionError(409, "The revision limit has been reached. Contact the operator before further changes.")
            for entry_id, before, after in changes:
                self.authorize_write(db, "entry", entry_id, new=before is None)
                if after:
                    self.validate_entry(after)
                    collision = db.execute("SELECT project_id FROM entries WHERE id=?", (entry_id,)).fetchone()
                    if collision and collision[0] != self.project:
                        raise CollectionError(409, "An entry with this identifier already exists.")
                    db.execute(
                        "INSERT INTO entries VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                        (entry_id, self.project, json.dumps(after, ensure_ascii=False)),
                    )
                else:
                    db.execute("DELETE FROM entries WHERE id=? AND project_id=?", (entry_id, self.project))
                db.execute(
                    "INSERT INTO revisions VALUES (?,?,?,?,?,?,?)",
                    (str(uuid4()), self.project, entry_id, action or ("create" if before is None else "delete" if after is None else "update"),
                     now(), json.dumps(before) if before else None, json.dumps(after) if after else None),
                )
            if changes:
                self.bump(db)

    def append_entry(self, entry: dict[str, str]):
        with self.lock():
            self.save_all([*self.load_all(), entry])

    @staticmethod
    def validate_entry(entry: dict) -> None:
        if not isinstance(entry, dict) or set(entry) != set(dataset.FIELDNAMES):
            raise CollectionError(422, "Terminology fields do not match the supported format.")
        try:
            parsed = DatasetEntry.model_validate(entry)
            EntryCreate.model_validate({k: v for k, v in entry.items() if k not in ("id", "timestamp", "audio_filename")})
            valid_id(parsed.id)
            media_name(parsed.audio_filename)
            datetime.fromisoformat(parsed.timestamp)
            if any(not isinstance(value, str) for value in entry.values()):
                raise ValueError("Invalid text value")
        except (ValueError, TypeError) as exc:
            raise CollectionError(422, "The terminology record is invalid.") from exc

    def check_audio_capacity(self, additional: int):
        files = list(self.audio_dir.iterdir())
        if any(not path.is_file() or path.is_symlink() for path in files):
            raise CollectionError(503, "The audio storage contains an unsupported file.")
        if len(files) >= 1000 or sum(path.stat().st_size for path in files) + additional > MAX_AUDIO_BYTES:
            raise CollectionError(409, "The workspace audio limit has been reached (128 MB or 1,000 recordings).")

    def load_coursework(self) -> ProjectProfile | None:
        with self.connection() as db:
            row = db.execute("SELECT data FROM coursework WHERE project_id=?", (self.project,)).fetchone()
        return ProjectProfile.model_validate_json(row["data"]) if row is not None else None

    def save_coursework(self, profile: ProjectProfile) -> None:
        with self.lock(), self.connection() as db:
            exists = db.execute("SELECT 1 FROM coursework WHERE project_id=?", (self.project,)).fetchone()
            self.authorize_write(db, "coursework", self.project, new=exists is None)
            db.execute(
                "INSERT INTO coursework VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET data=excluded.data",
                (self.project, profile.model_dump_json()),
            )
            self.bump(db)

    def load_analyzer_test(self, test_id: str) -> RecordedTest | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT id,project_id,data FROM analyzer_tests WHERE project_id=? AND id=?", (self.project, test_id),
            ).fetchone()
        return StoredAnalyzerTest.model_validate(dict(row)).data if row is not None else None

    def save_analyzer_test(self, record: RecordedTest) -> None:
        with self.lock(), self.connection() as db:
            self.authorize_write(db, "analyzer_test", record.id, new=True)
            db.execute(
                "INSERT INTO analyzer_tests VALUES (?,?,?)", (record.id, self.project, record.model_dump_json()),
            )
            self.bump(db)

    def load_analyzer_request(self, request_id: str) -> RecordedTest | None:
        return self.load_analyzer_test(request_id)

    def analyzer_test_identifier(self, request_id: str) -> str:
        return request_id

    def save_analyzer_request(self, request_id: str, record: RecordedTest) -> None:
        self.save_analyzer_test(record)

    def iter_analyzer_tests(self) -> Iterator[RecordedTest]:
        with self.connection() as db:
            for row in db.execute(
                "SELECT id,project_id,data FROM analyzer_tests WHERE project_id=? ORDER BY rowid DESC", (self.project,),
            ):
                yield StoredAnalyzerTest.model_validate(dict(row)).data

    def list_coursework_screenshots(self) -> list[dict[str, str]]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,name FROM screenshots WHERE project_id=? ORDER BY rowid", (self.project,),
            )]

    def read_coursework_screenshot(self, image_id: str) -> bytes:
        with self.connection() as db:
            row = db.execute(
                "SELECT content FROM screenshots WHERE id=? AND project_id=?", (image_id, self.project),
            ).fetchone()
        if row is None:
            raise CollectionError(404, "Screenshot not found.")
        return base64.b64decode(row["content"], validate=True)

    def save_coursework_screenshot(self, image_id: str, name: str, content: bytes) -> None:
        coursework_store.validate_stored_screenshot(content)
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authorize_write(db, "screenshot", image_id, new=True)
            if db.execute(
                "SELECT count(*) FROM screenshots WHERE project_id=?", (self.project,),
            ).fetchone()[0] >= coursework_store.MAX_SCREENSHOTS:
                raise CollectionError(
                    422, f"Keep at most {coursework_store.MAX_SCREENSHOTS} screenshots; remove one before uploading."
                )
            db.execute(
                "INSERT INTO screenshots VALUES (?,?,?,?)",
                (image_id, self.project, name, base64.b64encode(content).decode("ascii")),
            )
            self.bump(db)

    def delete_coursework_screenshot(self, image_id: str) -> None:
        with self.lock(), self.connection() as db:
            self.authorize_write(db, "screenshot", image_id)
            if db.execute(
                "DELETE FROM screenshots WHERE id=? AND project_id=?", (image_id, self.project),
            ).rowcount != 1:
                raise CollectionError(404, "Screenshot not found.")
            self.bump(db)

    def projects(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at,id")]

    def change_project(self, name: str, project_id: str | None = None) -> dict:
        name = name.strip()
        if not name:
            raise CollectionError(422, "Enter a project name.")
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if project_id:
                if db.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id)).rowcount != 1:
                    raise CollectionError(404, "Project not found.")
            else:
                if db.execute("SELECT count(*) FROM projects").fetchone()[0] >= 20:
                    raise CollectionError(409, "A workspace supports up to 20 projects.")
                project_id = str(uuid4())
                db.execute("INSERT INTO projects VALUES (?,?,?)", (project_id, name, now()))
            self.bump(db)
            return dict(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def delete_project(self, project_id: str):
        if project_id == "default":
            raise CollectionError(409, "The General project cannot be deleted.")
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if any(db.execute(f"SELECT 1 FROM {table} WHERE project_id=? LIMIT 1", (project_id,)).fetchone()
                   for table in ("entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests")):
                raise CollectionError(
                    409, "Only empty projects without saved work, coursework, analyzer tests or revision history can be deleted."
                )
            if db.execute("DELETE FROM projects WHERE id=?", (project_id,)).rowcount != 1:
                raise CollectionError(404, "Project not found.")
            self.bump(db)

    def histories(self, query: str = "") -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,title,created_at,updated_at FROM history WHERE project_id=? "
                "AND instr(lower(title),lower(?))>0 ORDER BY rowid DESC",
                (self.project, query),
            )]

    def history(self, entry_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM history WHERE id=? AND project_id=?", (entry_id, self.project)).fetchone()
        if row is None:
            raise CollectionError(404, "Saved work not found.")
        return {**dict(row), "content": json.loads(row["content"])}

    def save_history(self, payload: HistoryInput) -> dict:
        record = payload.document()
        timestamp = now()
        entry_id = str(uuid4())
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authorize_write(db, "history", entry_id, new=True)
            if db.execute("SELECT count(*) FROM history").fetchone()[0] >= MAX_HISTORY:
                raise CollectionError(409, "The saved-work limit is 500 items. Export or remove older items.")
            db.execute(
                "INSERT INTO history VALUES (?,?,?,?,?,?,?)",
                (entry_id, self.project, payload.kind, payload.title.strip(), json.dumps(record["content"]), timestamp, timestamp),
            )
            self.bump(db)
        return self.history(entry_id)

    def change_history(self, entry_id: str, title: str | None = None) -> None:
        with self.lock(), self.connection() as db:
            self.authorize_write(db, "history", entry_id)
            if title is None:
                cursor = db.execute("DELETE FROM history WHERE id=? AND project_id=?", (entry_id, self.project))
            else:
                if not title.strip():
                    raise CollectionError(422, "Enter a title.")
                cursor = db.execute("UPDATE history SET title=?,updated_at=? WHERE id=? AND project_id=?",
                                    (title.strip(), now(), entry_id, self.project))
            if cursor.rowcount != 1:
                raise CollectionError(404, "Saved work not found.")
            self.bump(db)

    def revisions(self, entry_id: str = "") -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM revisions WHERE project_id=? AND (?='' OR entry_id=?) ORDER BY rowid DESC LIMIT 200",
                (self.project, entry_id, entry_id),
            ).fetchall()
        return [
            {k: row[k] for k in ("id", "entry_id", "action", "timestamp")} |
            {"data": json.loads(row["after_data"] or row["before_data"])}
            for row in rows
        ]

    def restore_revision(self, revision_id: str, expected_version: int) -> dict:
        with self.lock():
            if self.version != expected_version:
                raise CollectionError(409, "The workspace changed. Refresh revisions before restoring.")
            with self.connection() as db:
                row = db.execute("SELECT * FROM revisions WHERE id=? AND project_id=?", (revision_id, self.project)).fetchone()
            if row is None:
                raise CollectionError(404, "Revision not found.")
            entry = json.loads(row["after_data"] or row["before_data"])
            with self.connection() as db:
                self.authorize_write(db, "entry", entry["id"])
            filename = entry["audio_filename"]
            if filename and not (self.audio_dir / media_name(filename)).is_file():
                raise CollectionError(409, "The recording required by this revision is missing.")
            entry["review_status"] = "unreviewed"
            from .collection import _check_duplicate
            entries = self.load_all()
            _check_duplicate(entries, entry["text"], entry["language"], entry["id"])
            restored = [item for item in entries if item["id"] != entry["id"]] + [entry]
            self.save_all(restored, action="restore")
            return {"entry": entry, "workspace_version": self.version}

    def export_document(self) -> dict:
        with self.lock(), self.connection() as db:
            document = {"format": 3, "version": self.version, "projects": self.projects()}
            for table in ("entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests"):
                document[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            return document

    @staticmethod
    def validate_document(document: object, *, combined: bool = False) -> dict:
        if not isinstance(document, dict):
            raise CollectionError(422, "Unsupported backup structure.")
        if document.get("format") == 4:
            from .shared_workspace import SharedWorkspaceStore
            return SharedWorkspaceStore.validate_document(document)
        base_fields = {"format", "version", "projects", "entries", "history", "revisions"}
        if document.get("format") == 1 and set(document) == base_fields:
            document = dict(document)
            document.update(format=2, coursework=[], screenshots=[])
        if document.get("format") == 2 and set(document) == base_fields | {"coursework", "screenshots"}:
            document = dict(document)
            document.update(format=3, analyzer_tests=[])
        if set(document) != base_fields | {"coursework", "screenshots", "analyzer_tests"}:
            raise CollectionError(422, "Unsupported backup structure.")
        if document["format"] != 3 or type(document["version"]) is not int or document["version"] < 0:
            raise CollectionError(422, "Unsupported backup version.")
        limits = {
            "projects": 20, "entries": MAX_ENTRIES, "history": MAX_HISTORY, "revisions": MAX_REVISIONS,
            "coursework": 20, "screenshots": 20 * coursework_store.MAX_SCREENSHOTS,
        }
        for table, limit in limits.items():
            if not isinstance(document[table], list) or (not combined and len(document[table]) > limit):
                raise CollectionError(422, "Backup record limits exceeded.")
        if not isinstance(document["analyzer_tests"], list):
            raise CollectionError(422, "Unsupported analyzer test records.")
        projects = set()
        identifiers: dict[str, set[str]] = {key: set() for key in limits}
        try:
            for project in document["projects"]:
                if set(project) != {"id", "name", "created_at"}:
                    raise ValueError("Invalid project")
                valid_id(project["id"], default=True)
                ProjectInput(name=project["name"])
                datetime.fromisoformat(project["created_at"])
                projects.add(project["id"])
            if len(projects) != len(document["projects"]) or "default" not in projects:
                raise ValueError("Missing or duplicate default project")
            columns = {
                "entries": {"id", "project_id", "data"},
                "history": {"id", "project_id", "kind", "title", "content", "created_at", "updated_at"},
                "revisions": {"id", "project_id", "entry_id", "action", "timestamp", "before_data", "after_data"},
            }
            for table in columns:
                for row in document[table]:
                    if set(row) != columns[table] or row["project_id"] not in projects:
                        raise ValueError("Invalid record")
                    valid_id(row["id"])
                    if row["id"] in identifiers[table]:
                        raise ValueError("Duplicate identifier")
                    identifiers[table].add(row["id"])
                    if table == "entries":
                        entry = json.loads(row["data"])
                        WorkspaceStore.validate_entry(entry)
                        if entry["id"] != row["id"]:
                            raise ValueError("Entry ID mismatch")
                    elif table == "history":
                        HistoryInput(kind=row["kind"], title=row["title"], content=json.loads(row["content"])).document()
                        datetime.fromisoformat(row["created_at"])
                        datetime.fromisoformat(row["updated_at"])
                    else:
                        if row["action"] not in ("create", "update", "delete", "restore"):
                            raise ValueError("Invalid revision action")
                        valid_id(row["entry_id"])
                        datetime.fromisoformat(row["timestamp"])
                        if not row["before_data"] and not row["after_data"]:
                            raise ValueError("Empty revision")
                        for key in ("before_data", "after_data"):
                            if row[key] is not None:
                                entry = json.loads(row[key])
                                WorkspaceStore.validate_entry(entry)
                                if entry["id"] != row["entry_id"]:
                                    raise ValueError("Revision ID mismatch")
            for row in document["coursework"]:
                if set(row) != {"project_id", "data"} or row["project_id"] not in projects:
                    raise ValueError("Invalid coursework profile")
                if row["project_id"] in identifiers["coursework"]:
                    raise ValueError("Duplicate coursework profile")
                identifiers["coursework"].add(row["project_id"])
                profile = ProjectProfile.model_validate_json(row["data"])
                analyze_grammar(profile.grammar)
            screenshot_counts: dict[str, int] = {}
            for row in document["screenshots"]:
                if set(row) != {"id", "project_id", "name", "content"} or row["project_id"] not in projects:
                    raise ValueError("Invalid screenshot")
                if re.fullmatch(r"[a-f0-9]{32}", row["id"]) is None or row["id"] in identifiers["screenshots"]:
                    raise ValueError("Invalid or duplicate screenshot ID")
                identifiers["screenshots"].add(row["id"])
                if not isinstance(row["name"], str) or not row["name"].strip() or len(row["name"]) > 120:
                    raise ValueError("Invalid screenshot name")
                if not isinstance(row["content"], str) or len(row["content"]) > 2800000:
                    raise ValueError("Invalid screenshot content")
                coursework_store.validate_stored_screenshot(base64.b64decode(row["content"], validate=True))
                count = screenshot_counts.get(row["project_id"], 0) + 1
                if not combined and count > coursework_store.MAX_SCREENSHOTS:
                    raise ValueError("Too many project screenshots")
                screenshot_counts[row["project_id"]] = count
            test_identifiers = set()
            for row in document["analyzer_tests"]:
                saved = StoredAnalyzerTest.model_validate(row)
                key = (saved.project_id, saved.id)
                if saved.project_id not in projects or key in test_identifiers:
                    raise ValueError("Invalid project or duplicate analyzer test")
                if read_grammar(saved.data.grammar_source) != saved.data.grammar.original:
                    raise ValueError("Saved grammar source does not match its original rules")
                test_identifiers.add(key)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise CollectionError(422, "The backup contains invalid workspace records.") from exc
        return document

    def import_document(self, document: dict, expected_version: int):
        document = self.validate_document(document)
        if document["format"] != 3:
            raise CollectionError(422, "Shared backups must be restored into the shared workspace.")
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authorize_import(document)
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            if version != expected_version:
                raise CollectionError(409, "Your workspace changed after preview. Preview the backup again.")
            for table in ("entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests", "projects"):
                db.execute(f"DELETE FROM {table}")
            for table in ("projects", "entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests"):
                for row in document[table]:
                    columns = list(row)
                    db.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                        tuple(row[column] for column in columns),
                    )
            self.bump(db)


def current_workspace() -> WorkspaceStore:
    workspace = _workspace.get()
    if workspace is None:
        raise CollectionError(401, "The shared workspace requires a signed-in account.")
    return workspace


def install_workspace(app: FastAPI, data_dir: Path) -> Callable[[UserIdentity, Request], AbstractAsyncContextManager[WorkspaceStore]]:
    from .ownership import use_ownership
    from .shared_workspace import SharedWorkspaceStore

    router = APIRouter(prefix="/api/workspace", tags=["Shared workspace"])

    @router.get("/projects")
    def projects(request: Request):
        return storage_operation(lambda: {
            "projects": current_workspace().projects(), "default_project_id": "default", "shared": True,
            "registered_users": request.app.state.auth_store.registered_user_count(),
        })

    @router.post("/projects", status_code=201)
    def create_project(payload: ProjectInput):
        return storage_operation(lambda: current_workspace().change_project(payload.name))

    @router.patch("/projects/{project_id}")
    def rename_project(project_id: str, payload: ProjectInput):
        return storage_operation(lambda: current_workspace().change_project(payload.name, project_id))

    @router.delete("/projects/{project_id}", status_code=204)
    def remove_project(project_id: str):
        storage_operation(lambda: current_workspace().delete_project(project_id))

    @router.get("/history")
    def history(query: str = Query(default="", max_length=200)):
        return storage_operation(lambda: {"entries": current_workspace().histories(query)})

    @router.post("/history", status_code=201)
    def save_history(payload: HistoryInput):
        return storage_operation(lambda: current_workspace().save_history(payload))

    @router.get("/history/{entry_id}")
    def read_history(entry_id: str):
        return storage_operation(lambda: current_workspace().history(entry_id))

    @router.patch("/history/{entry_id}")
    def rename_history(entry_id: str, payload: ProjectInput):
        storage_operation(lambda: current_workspace().change_history(entry_id, payload.name))
        return storage_operation(lambda: current_workspace().history(entry_id))

    @router.delete("/history/{entry_id}", status_code=204)
    def remove_history(entry_id: str):
        storage_operation(lambda: current_workspace().change_history(entry_id))

    @router.get("/revisions")
    def revisions(entry_id: str = Query(default="", max_length=36)):
        return storage_operation(lambda: {
            "revisions": current_workspace().revisions(entry_id), "workspace_version": current_workspace().version,
        })

    @router.post("/revisions/{revision_id}/restore")
    def restore_revision(revision_id: str, payload: RestoreRevision):
        return storage_operation(lambda: current_workspace().restore_revision(revision_id, payload.expected_version))

    app.include_router(router)

    @asynccontextmanager
    async def workspace_context(user: UserIdentity, request: Request) -> AsyncIterator[WorkspaceStore]:
        # Old bookmarks/clients can name a former project, but no header partitions shared data.
        for project in (request.headers.get("x-mboa-project"), request.query_params.get("project")):
            if project:
                valid_id(project, default=True)
        workspace = await run_in_threadpool(SharedWorkspaceStore, data_dir, user.id, user.display_name)
        token = _workspace.set(workspace)
        try:
            with dataset.use_storage(workspace), coursework_store.use_storage(workspace), use_ownership(workspace):
                yield workspace
        finally:
            _workspace.reset(token)

    return workspace_context
