import json
import logging
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from filelock import FileLock

from .auth import private_directory
from .collection import CollectionError
from .file_storage import atomic_write
from .workspaces import WorkspaceStore, media_name

logger = logging.getLogger(__name__)
CONTENT_TABLES = ("entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests")


def _sources(data_dir: Path) -> list[Path]:
    root = data_dir / "workspaces"
    if not root.exists():
        return []
    paths = []
    for directory in sorted(root.iterdir()):
        try:
            canonical = str(UUID(directory.name)) == directory.name
        except ValueError:
            canonical = False
        if not canonical:
            continue
        path = directory / "workspace.sqlite3"
        if directory.is_symlink() or path.is_symlink():
            raise CollectionError(503, "A legacy workspace uses a linked storage path; migration stopped.")
        if path.is_file():
            paths.append(path)
    return paths


def _read_source(path: Path) -> tuple[dict, dict | None]:
    from .workspace_backups import BackupSettings

    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        document = {
            "format": 3, "version": int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]),
            "projects": [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at,id")],
        }
        for table in CONTENT_TABLES:
            document[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")] if table in tables else []
        row = db.execute("SELECT value FROM meta WHERE key='backup:settings'").fetchone()
        settings = BackupSettings.model_validate_json(row[0]).model_dump() if row is not None else None
    return WorkspaceStore.validate_document(document), settings


def migrate_workspaces(store: WorkspaceStore, data_dir: Path, db: sqlite3.Connection) -> None:
    """Copy legacy data once; originals remain untouched as migration archives."""
    sources = _sources(data_dir)
    names = {}
    auth_path = data_dir / "auth.sqlite3"
    if auth_path.is_file():
        if auth_path.is_symlink():
            raise CollectionError(503, "The account storage path is invalid.")
        with closing(sqlite3.connect(auth_path.as_uri() + "?mode=ro", uri=True)) as accounts:
            names = dict(accounts.execute("SELECT id,display_name FROM users"))
    created_media: list[Path] = []
    used: dict[str, set[str]] = {}
    identifiers: dict[tuple[str, str, str, str], str] = {}

    def identifier(owner: str, project: str, kind: str, original: str) -> str:
        key = (owner, project, kind, original)
        if key in identifiers:
            return identifiers[key]
        occupied = used.setdefault(kind, set())
        candidate = original
        attempt = 0
        while candidate in occupied:
            candidate_uuid = uuid5(NAMESPACE_URL, f"mboa-shared:{key}:{attempt}")
            candidate = candidate_uuid.hex if kind == "screenshot" else str(candidate_uuid)
            attempt += 1
        occupied.add(candidate)
        identifiers[key] = candidate
        return candidate

    def own(kind: str, record_id: str, owner: str) -> None:
        db.execute(
            "INSERT OR IGNORE INTO ownership VALUES (?,?,?,?)",
            (kind, record_id, owner, names.get(owner, "Former account")),
        )

    profiles = []
    schedules = []
    counts = {table: 0 for table in CONTENT_TABLES}
    try:
        with ExitStack() as locks:
            for path in sources:
                locks.enter_context(FileLock(str(path.parent / "workspace.lock"), timeout=10))
            for path in sources:
                owner = path.parent.name
                document, settings = _read_source(path)
                if settings is not None and settings["automatic"]:
                    schedules.append((owner, settings))
                audio_map = {}
                audio_dir = path.parent / "audio"
                if audio_dir.is_symlink():
                    raise CollectionError(503, "A legacy audio directory is linked; migration stopped.")
                for source in sorted(audio_dir.iterdir()) if audio_dir.exists() else []:
                    if not source.is_file() or source.is_symlink():
                        raise CollectionError(503, "Legacy audio storage contains an unsupported file.")
                    name = media_name(source.name)
                    content = source.read_bytes()
                    target = store.audio_dir / name
                    if target.is_symlink():
                        raise CollectionError(503, "Shared audio storage contains a linked file.")
                    if target.exists() and target.read_bytes() != content:
                        name = uuid5(NAMESPACE_URL, f"mboa-audio:{owner}:{name}").hex + source.suffix
                        target = store.audio_dir / name
                    if target.exists() and (target.is_symlink() or target.read_bytes() != content):
                        raise CollectionError(409, "A migrated audio identifier conflicts with an existing file.")
                    if not target.exists():
                        atomic_write(target, content)
                        created_media.append(target)
                    audio_map[source.name] = name

                def entry_data(content: str, project: str) -> str:
                    entry = json.loads(content)
                    entry["id"] = identifier(owner, project, "entry", entry["id"])
                    if entry["audio_filename"]:
                        if entry["audio_filename"] not in audio_map:
                            raise CollectionError(409, "A legacy recording is missing; no shared records were imported.")
                        entry["audio_filename"] = audio_map[entry["audio_filename"]]
                    own("entry", entry["id"], owner)
                    return json.dumps(entry, ensure_ascii=False)

                for table in CONTENT_TABLES:
                    counts[table] += len(document[table])
                for row in document["entries"]:
                    content = entry_data(row["data"], row["project_id"])
                    record_id = identifier(owner, row["project_id"], "entry", row["id"])
                    db.execute("INSERT INTO entries VALUES (?,'default',?)", (record_id, content))
                for row in document["revisions"]:
                    project = row["project_id"]
                    record_id = identifier(owner, project, "revision", row["id"])
                    entry_id = identifier(owner, project, "entry", row["entry_id"])
                    before = entry_data(row["before_data"], project) if row["before_data"] else None
                    after = entry_data(row["after_data"], project) if row["after_data"] else None
                    db.execute(
                        "INSERT INTO revisions VALUES (?,'default',?,?,?,?,?)",
                        (record_id, entry_id, row["action"], row["timestamp"], before, after),
                    )
                for row in document["history"]:
                    record_id = identifier(owner, row["project_id"], "history", row["id"])
                    db.execute(
                        "INSERT INTO history VALUES (?,'default',?,?,?,?,?)",
                        (record_id, row["kind"], row["title"], row["content"], row["created_at"], row["updated_at"]),
                    )
                    own("history", record_id, owner)
                for row in document["screenshots"]:
                    record_id = identifier(owner, row["project_id"], "screenshot", row["id"])
                    db.execute(
                        "INSERT INTO screenshots VALUES (?,'default',?,?)",
                        (record_id, row["name"], row["content"]),
                    )
                    own("screenshot", record_id, owner)
                for row in document["analyzer_tests"]:
                    record_id = identifier(owner, row["project_id"], "analyzer_test", row["id"])
                    record = json.loads(row["data"])
                    record["id"] = record_id
                    db.execute(
                        "INSERT INTO analyzer_tests VALUES (?,'default',?)",
                        (record_id, json.dumps(record, ensure_ascii=False)),
                    )
                    own("analyzer_test", record_id, owner)
                    db.execute("INSERT INTO test_requests VALUES (?,?,?)", (owner, row["id"], record_id))
                projects = {row["id"]: row for row in document["projects"]}
                for row in document["coursework"]:
                    project = projects[row["project_id"]]
                    db.execute(
                        "INSERT INTO legacy_profiles VALUES (?,?,?,?)",
                        (owner, project["id"], project["name"], row["data"]),
                    )
                    profiles.append((project["created_at"], owner, project["id"], row["data"]))
                db.execute(
                    "INSERT INTO migration_sources VALUES (?,?,?)",
                    (owner, document["version"], json.dumps(document["projects"], ensure_ascii=False)),
                )
            if profiles:
                _, owner, _, content = min(profiles)
                db.execute("INSERT INTO coursework VALUES ('default',?)", (content,))
                own("coursework", "default", owner)
            if schedules:
                settings = {
                    "automatic": True,
                    "interval_hours": min(settings["interval_hours"] for _, settings in schedules),
                    "keep_last": max(settings["keep_last"] for _, settings in schedules),
                }
                db.execute("INSERT INTO meta VALUES ('backup:settings',?)", (json.dumps(settings),))
                own("backup_settings", "default", schedules[0][0])
            db.execute("UPDATE projects SET name='Shared workspace' WHERE id='default'")
            db.execute("INSERT INTO meta VALUES ('shared:migration',?)", (json.dumps(counts),))
            db.execute("INSERT INTO meta VALUES ('shared:initialized','1')")
            store.bump(db)
    except (CollectionError, OSError, sqlite3.Error, ValueError):
        for path in created_media:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove an uncommitted migration audio copy.")
        raise
