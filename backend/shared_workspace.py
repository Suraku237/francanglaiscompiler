import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid5

from .analyzer_models import RecordedTest, StoredAnalyzerTest
from .collection import CollectionError
from .coursework_models import ProjectProfile
from .ownership import Ownership
from .shared_migration import CONTENT_TABLES, migrate_workspaces
from .workspaces import WorkspaceStore, valid_id

SYSTEM_OWNER_ID = "00000000-0000-0000-0000-000000000000"
SHARED_TABLES = ("ownership", "test_requests", "legacy_profiles")
CONTENT_KINDS = {"entry", "history", "coursework", "screenshot", "analyzer_test"}


class SharedWorkspaceStore(WorkspaceStore):
    def __init__(self, data_dir: Path, user_id: str, owner_name: str = "", *, system: bool = False):
        self.owner_name = owner_name
        self.system = system
        super().__init__(data_dir, user_id)
        with self.lock(), self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS ownership (
                    kind TEXT NOT NULL,record_id TEXT NOT NULL,owner_id TEXT NOT NULL,owner_name TEXT NOT NULL,
                    PRIMARY KEY (kind,record_id)
                );
                CREATE TABLE IF NOT EXISTS test_requests (
                    owner_id TEXT NOT NULL,request_id TEXT NOT NULL,test_id TEXT NOT NULL,
                    PRIMARY KEY (owner_id,request_id,test_id)
                );
                CREATE TABLE IF NOT EXISTS legacy_profiles (
                    owner_id TEXT NOT NULL,project_id TEXT NOT NULL,project_name TEXT NOT NULL,data TEXT NOT NULL,
                    PRIMARY KEY (owner_id,project_id)
                );
                CREATE TABLE IF NOT EXISTS migration_sources (
                    owner_id TEXT PRIMARY KEY,source_version INTEGER NOT NULL,projects TEXT NOT NULL
                );
            """)
            if db.execute("SELECT 1 FROM meta WHERE key='shared:initialized'").fetchone() is None:
                db.execute("BEGIN IMMEDIATE")
                migrate_workspaces(self, data_dir, db)

    def storage_root(self, data_dir: Path, user_id: str) -> Path:
        return data_dir / "shared-workspace"

    def authorize_write(
        self, db: sqlite3.Connection, kind: str, identifier: str, *, new: bool = False,
    ) -> None:
        row = db.execute(
            "SELECT owner_id FROM ownership WHERE kind=? AND record_id=?", (kind, identifier),
        ).fetchone()
        if row is not None:
            if row["owner_id"] != self.user_id and not self.system:
                raise CollectionError(403, "Only the creator can edit or delete this shared record.")
        elif new:
            db.execute(
                "INSERT INTO ownership VALUES (?,?,?,?)",
                (kind, identifier, self.user_id, self.owner_name),
            )
        else:
            raise CollectionError(404, "This shared record no longer exists.")

    def require_owner(self, kind: str, identifier: str) -> None:
        with self.lock(), self.connection() as db:
            self.authorize_write(db, kind, identifier)

    def ownership(self, kind: str, identifier: str) -> Ownership:
        with self.connection() as db:
            row = db.execute(
                "SELECT owner_id,owner_name FROM ownership WHERE kind=? AND record_id=?", (kind, identifier),
            ).fetchone()
            if row is None:
                if kind == "coursework" and db.execute("SELECT 1 FROM coursework").fetchone() is None:
                    return Ownership(owner_id=None, owner_name="", can_edit=True)
                raise CollectionError(503, "Shared record ownership is unavailable. Contact the operator.")
        return Ownership(
            owner_id=row["owner_id"], owner_name=row["owner_name"],
            can_edit=row["owner_id"] == self.user_id,
        )

    def change_project(self, name: str, project_id: str | None = None) -> dict:
        raise CollectionError(409, "All users now use one shared workspace; separate projects are not supported.")

    def delete_project(self, project_id: str) -> None:
        raise CollectionError(409, "The shared workspace cannot be deleted.")

    def save_backup_settings(self, settings: dict) -> None:
        with self.lock(), self.connection() as db:
            self.authorize_write(db, "backup_settings", "default", new=True)
            db.execute(
                "INSERT INTO meta VALUES ('backup:settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(settings),),
            )
            self.bump(db)

    def load_analyzer_request(self, request_id: str) -> RecordedTest | None:
        with self.connection() as db:
            rows = db.execute(
                "SELECT test_id FROM test_requests WHERE owner_id=? AND request_id=?",
                (self.user_id, request_id),
            ).fetchall()
        if len(rows) > 1:
            raise CollectionError(409, "This request was used in multiple former projects. Start a new test.")
        return self.load_analyzer_test(rows[0]["test_id"]) if rows else None

    def analyzer_test_identifier(self, request_id: str) -> str:
        return str(uuid5(UUID(self.user_id), request_id))

    def save_analyzer_request(self, request_id: str, record: RecordedTest) -> None:
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authorize_write(db, "analyzer_test", record.id, new=True)
            db.execute(
                "INSERT INTO analyzer_tests VALUES (?,'default',?)", (record.id, record.model_dump_json()),
            )
            db.execute("INSERT INTO test_requests VALUES (?,?,?)", (self.user_id, request_id, record.id))
            self.bump(db)

    def iter_analyzer_tests(self) -> Iterator[RecordedTest]:
        with self.connection() as db:
            for row in db.execute(
                "SELECT id,project_id,data FROM analyzer_tests "
                "ORDER BY julianday(json_extract(data,'$.created_at')) DESC,rowid DESC",
            ):
                yield StoredAnalyzerTest.model_validate(dict(row)).data

    def export_document(self) -> dict:
        with self.lock(), self.connection() as db:
            document = super().export_document()
            document["format"] = 4
            for table in SHARED_TABLES:
                query = " WHERE kind IN ('entry','history','coursework','screenshot','analyzer_test')" if table == "ownership" else ""
                document[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table}{query} ORDER BY rowid")]
            return document

    @staticmethod
    def validate_document(document: object, *, combined: bool = False) -> dict:
        base_fields = {"format", "version", "projects", *CONTENT_TABLES}
        if not isinstance(document, dict) or document.get("format") != 4:
            raise CollectionError(422, "Shared-workspace restoration requires a format-4 backup with creator information.")
        if set(document) != base_fields | set(SHARED_TABLES):
            raise CollectionError(422, "Unsupported shared backup structure.")
        # Merged snapshots can exceed the former per-account record limits.
        WorkspaceStore.validate_document(
            {key: 3 if key == "format" else document[key] for key in base_fields}, combined=True,
        )
        if len(document["projects"]) != 1 or document["projects"][0]["id"] != "default":
            raise CollectionError(422, "Shared backups must contain one combined workspace.")
        try:
            owners = {}
            for row in document["ownership"]:
                if set(row) != {"kind", "record_id", "owner_id", "owner_name"} or row["kind"] not in CONTENT_KINDS:
                    raise ValueError("Invalid ownership row")
                valid_id(row["owner_id"])
                if not isinstance(row["owner_name"], str) or len(row["owner_name"]) > 100:
                    raise ValueError("Invalid creator name")
                if row["kind"] == "coursework":
                    if row["record_id"] != "default":
                        raise ValueError("Invalid shared grammar")
                elif row["kind"] == "screenshot":
                    if re.fullmatch(r"[a-f0-9]{32}", row["record_id"]) is None:
                        raise ValueError("Invalid screenshot")
                else:
                    valid_id(row["record_id"])
                key = (row["kind"], row["record_id"])
                if key in owners:
                    raise ValueError("Duplicate owner")
                owners[key] = row["owner_id"]
            for table, kind, column in (
                ("entries", "entry", "id"), ("revisions", "entry", "entry_id"),
                ("history", "history", "id"), ("coursework", "coursework", "project_id"),
                ("screenshots", "screenshot", "id"), ("analyzer_tests", "analyzer_test", "id"),
            ):
                if any(row["project_id"] != "default" or (kind, row[column]) not in owners for row in document[table]):
                    raise ValueError("A shared record has no creator")
            requests = set()
            tests = {row["id"] for row in document["analyzer_tests"]}
            for row in document["test_requests"]:
                if set(row) != {"owner_id", "request_id", "test_id"}:
                    raise ValueError("Invalid request identity")
                valid_id(row["request_id"])
                if row["test_id"] not in tests or owners[("analyzer_test", row["test_id"])] != row["owner_id"]:
                    raise ValueError("Request creator mismatch")
                key = (row["owner_id"], row["request_id"], row["test_id"])
                if key in requests:
                    raise ValueError("Duplicate test request")
                requests.add(key)
            profiles = set()
            for row in document["legacy_profiles"]:
                if set(row) != {"owner_id", "project_id", "project_name", "data"}:
                    raise ValueError("Invalid archived profile")
                valid_id(row["owner_id"])
                valid_id(row["project_id"], default=True)
                if not isinstance(row["project_name"], str) or not 1 <= len(row["project_name"]) <= 100:
                    raise ValueError("Invalid archived project")
                ProjectProfile.model_validate_json(row["data"])
                key = (row["owner_id"], row["project_id"])
                if key in profiles:
                    raise ValueError("Duplicate archived profile")
                profiles.add(key)
        except (KeyError, TypeError, ValueError) as exc:
            raise CollectionError(422, "The backup contains invalid shared ownership records.") from exc
        return document

    def authorize_import(self, document: dict) -> None:
        document = self.validate_document(document)
        if self.system:
            return
        current = self.export_document()
        if document["projects"] != current["projects"] or document["legacy_profiles"] != current["legacy_profiles"]:
            raise CollectionError(403, "Restoring cannot change the shared workspace or its archived original profiles.")
        previous_owners = {(row["kind"], row["record_id"]): row for row in current["ownership"]}
        next_owners = {(row["kind"], row["record_id"]): row for row in document["ownership"]}
        for key, row in next_owners.items():
            previous = previous_owners.get(key)
            if (previous is not None and row != previous) or (previous is None and row["owner_id"] != self.user_id):
                raise CollectionError(403, "A backup cannot change a record's creator or claim another user's records.")

        def allowed(row: dict, kind: str, column: str, owners: dict) -> bool:
            return owners[(kind, row[column])]["owner_id"] == self.user_id

        for table, kind, identity, column in (
            ("entries", "entry", "id", "id"), ("revisions", "entry", "id", "entry_id"),
            ("history", "history", "id", "id"), ("coursework", "coursework", "project_id", "project_id"),
            ("screenshots", "screenshot", "id", "id"), ("analyzer_tests", "analyzer_test", "id", "id"),
        ):
            before = {row[identity]: row for row in current[table]}
            after = {row[identity]: row for row in document[table]}
            for key in before.keys() | after.keys():
                old, new = before.get(key), after.get(key)
                if old == new:
                    continue
                if ((old is not None and not allowed(old, kind, column, previous_owners)) or
                        (new is not None and not allowed(new, kind, column, next_owners))):
                    raise CollectionError(403, "Restoring this backup would edit or delete another creator's shared records.")
        other_requests = lambda rows: {
            (row["owner_id"], row["request_id"], row["test_id"]) for row in rows if row["owner_id"] != self.user_id
        }
        if other_requests(current["test_requests"]) != other_requests(document["test_requests"]):
            raise CollectionError(403, "Restoring cannot replace another user's saved-test request history.")

    def import_document(self, document: dict, expected_version: int) -> None:
        document = self.validate_document(document)
        with self.lock(), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.version != expected_version:
                raise CollectionError(409, "The shared workspace changed after preview. Preview the backup again.")
            self.authorize_import(document)
            for table in CONTENT_TABLES:
                db.execute(f"DELETE FROM {table}")
                for row in document[table]:
                    columns = list(row)
                    db.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                        tuple(row[column] for column in columns),
                    )
            for row in document["ownership"]:
                db.execute(
                    "INSERT OR IGNORE INTO ownership VALUES (?,?,?,?)",
                    (row["kind"], row["record_id"], row["owner_id"], row["owner_name"]),
                )
            db.execute("DELETE FROM test_requests")
            for row in document["test_requests"]:
                db.execute("INSERT INTO test_requests VALUES (?,?,?)", (row["owner_id"], row["request_id"], row["test_id"]))
            db.execute("DELETE FROM legacy_profiles")
            for row in document["legacy_profiles"]:
                db.execute(
                    "INSERT INTO legacy_profiles VALUES (?,?,?,?)",
                    (row["owner_id"], row["project_id"], row["project_name"], row["data"]),
                )
            self.bump(db)
