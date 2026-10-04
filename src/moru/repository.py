"""SQLite conversation history. Each public write is one transaction."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from moru.domain import GenerationSettings, Image, Project, Request
from moru.errors import MoruError

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    active_leaf_id TEXT REFERENCES images(id), fork_image_id TEXT REFERENCES images(id)
);
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
    text TEXT NOT NULL, created_at TEXT NOT NULL,
    base_image_id TEXT REFERENCES images(id), kind TEXT NOT NULL,
    settings TEXT NOT NULL, status TEXT NOT NULL, error_code TEXT
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
    request_id TEXT NOT NULL UNIQUE REFERENCES requests(id),
    parent_image_id TEXT REFERENCES images(id), prompt TEXT NOT NULL,
    image_path TEXT NOT NULL, settings TEXT NOT NULL, created_at TEXT NOT NULL,
    generation_method TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS images_parent ON images(project_id, parent_image_id);
CREATE INDEX IF NOT EXISTS requests_project ON requests(project_id);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_images BEFORE UPDATE ON images
BEGIN SELECT RAISE(ABORT, 'image history is immutable'); END;
"""


class Repository:
    def __init__(self, path: Path):
        self._lock = RLock()
        self._transaction_depth = 0
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript(SCHEMA)
            with self._db:
                self._db.execute(
                    "UPDATE requests SET status='failed', error_code='GENERATION_INTERRUPTED' "
                    "WHERE status='pending'"
                )
        except (OSError, sqlite3.Error) as exc:
            raise MoruError("DATABASE_FAILED") from exc

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._transaction_depth += 1
            try:
                if self._transaction_depth == 1:
                    with self._db:
                        yield self._db
                else:
                    yield self._db
            except sqlite3.Error as exc:
                raise MoruError("DATABASE_FAILED") from exc
            finally:
                self._transaction_depth -= 1

    def close(self):
        with self._lock:
            self._db.close()

    def create_project(self, project: Project):
        with self._transaction() as db:
            db.execute(
                "INSERT INTO projects VALUES (?, ?, NULL, NULL)", (project.id, project.created_at)
            )
            db.execute(
                "INSERT OR REPLACE INTO preferences VALUES ('current_project', ?)",
                (json.dumps(project.id),),
            )

    def list_projects(self) -> list[Project]:
        with self._transaction() as db:
            return [
                Project(**dict(row))
                for row in db.execute("SELECT * FROM projects ORDER BY rowid DESC")
            ]

    def get_project(self, project_id: str) -> Project:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise MoruError("NOT_FOUND")
            return Project(**dict(row))

    def set_current_project(self, project_id: str):
        self.get_project(project_id)
        self.set_preference("current_project", project_id)

    def set_fork(self, project_id: str, image_id: str | None):
        with self._transaction() as db:
            self.get_project(project_id)
            if image_id is not None:
                self.require_image(project_id, image_id)
            db.execute("UPDATE projects SET fork_image_id=? WHERE id=?", (image_id, project_id))

    def select_branch(self, project_id: str, image_id: str):
        with self._transaction() as db:
            self.require_image(project_id, image_id)
            leaf = image_id
            while children := self.children(project_id, leaf):
                leaf = children[-1].id
            db.execute(
                "UPDATE projects SET active_leaf_id=?, fork_image_id=NULL WHERE id=?",
                (leaf, project_id),
            )

    def add_request(self, request: Request):
        with self._transaction() as db:
            self.get_project(request.project_id)
            if request.base_image_id is not None:
                self.require_image(request.project_id, request.base_image_id)
            db.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request.id,
                    request.project_id,
                    request.text,
                    request.created_at,
                    request.base_image_id,
                    request.kind,
                    json.dumps(asdict(request.settings)),
                    request.status,
                    request.error_code,
                ),
            )

    def get_request(self, request_id: str) -> Request:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise MoruError("NOT_FOUND")
            return self._request(row)

    def unfinished_requests(self, project_id: str) -> list[Request]:
        with self._transaction() as db:
            return [
                self._request(row)
                for row in db.execute(
                    "SELECT * FROM requests WHERE project_id=? AND status!='completed' "
                    "ORDER BY rowid",
                    (project_id,),
                )
            ]

    def set_request_status(self, request_id: str, status: str, error_code: str | None = None):
        with self._transaction() as db:
            request = self.get_request(request_id)
            if request.status == "completed":
                raise MoruError("INVALID_REQUEST")
            db.execute(
                "UPDATE requests SET status=?, error_code=? WHERE id=?",
                (status, error_code, request_id),
            )

    def complete_generation(self, image: Image):
        with self._transaction() as db:
            request = self.get_request(image.request_id)
            if (
                request.status != "pending"
                or request.project_id != image.project_id
                or request.base_image_id != image.parent_image_id
                or request.kind != image.generation_method
                or image.settings.seed is None
            ):
                raise MoruError("DATABASE_FAILED")
            db.execute(
                "INSERT INTO images VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    image.id,
                    image.project_id,
                    image.request_id,
                    image.parent_image_id,
                    image.prompt,
                    image.image_path,
                    json.dumps(asdict(image.settings)),
                    image.created_at,
                    image.generation_method,
                ),
            )
            db.execute(
                "UPDATE requests SET status='completed', error_code=NULL WHERE id=?",
                (image.request_id,),
            )
            db.execute(
                "UPDATE projects SET active_leaf_id=?, fork_image_id=NULL WHERE id=?",
                (image.id, image.project_id),
            )

    def get_image(self, image_id: str) -> Image:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
            if row is None:
                raise MoruError("NOT_FOUND")
            return self._image(row)

    def require_image(self, project_id: str, image_id: str) -> Image:
        image = self.get_image(image_id)
        if image.project_id != project_id:
            raise MoruError("NOT_FOUND")
        return image

    def children(self, project_id: str, parent_id: str | None) -> list[Image]:
        with self._transaction() as db:
            return [
                self._image(row)
                for row in db.execute(
                    "SELECT * FROM images WHERE project_id=? AND parent_image_id IS ? "
                    "ORDER BY rowid",
                    (project_id, parent_id),
                )
            ]

    def active_path(self, project_id: str) -> list[Image]:
        with self._transaction():
            current = self.get_project(project_id).active_leaf_id
            path = []
            while current is not None:
                image = self.require_image(project_id, current)
                path.append(image)
                current = image.parent_image_id
            return list(reversed(path))

    def get_preference(self, key: str, default=None):
        with self._transaction() as db:
            row = db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_preference(self, key: str, value):
        self.set_preferences({key: value})

    def set_preferences(self, values: dict):
        with self._transaction() as db:
            db.executemany(
                "INSERT OR REPLACE INTO preferences VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in values.items()],
            )

    @staticmethod
    def _request(row) -> Request:
        values = dict(row)
        values["settings"] = GenerationSettings(**json.loads(values["settings"]))
        return Request(**values)

    @staticmethod
    def _image(row) -> Image:
        values = dict(row)
        values["settings"] = GenerationSettings(**json.loads(values["settings"]))
        return Image(**values)
