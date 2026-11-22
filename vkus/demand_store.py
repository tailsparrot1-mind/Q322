"""Private, per-installation archive of Vkus search results.

The database is local to the operating-system user's ~/.vkus directory. It is
not uploaded to Supabase and is not shared between Vkus installations.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_PATH = Path.home() / ".vkus" / "demand.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _value(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _normal_kind(value: str) -> str:
    value = (value or '').strip().lower()
    if value in ('comment', 'comments', 'reply'):
        return 'comment'
    return 'post'


def _external_key(item: dict[str, Any], default_kind: str = 'post') -> str:
    body = " ".join(_value(item, "comment_text", "text").lower().split())
    url = _value(item, "post_url", "url")
    kind = _normal_kind(_value(item, "kind", default=default_kind))
    return hashlib.sha256(f"vk\x1f{kind}\x1f{url}\x1f{body}".encode("utf-8")).hexdigest()


class DemandStore:
    """SQLite archive scoped to one local Vkus installation / OS user."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self.workspace_id = self._initialize()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> str:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_runs (
                    run_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    region TEXT,
                    city TEXT,
                    mode TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS demand_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    external_key TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'vk',
                    kind TEXT NOT NULL,
                    body TEXT NOT NULL,
                    interest TEXT,
                    date_text TEXT,
                    source_url TEXT,
                    profile_url TEXT,
                    author_name TEXT,
                    username TEXT,
                    city TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(workspace_id, external_key)
                );
                CREATE TABLE IF NOT EXISTS search_run_items (
                    run_id TEXT NOT NULL REFERENCES search_runs(run_id) ON DELETE CASCADE,
                    item_id INTEGER NOT NULL REFERENCES demand_items(item_id) ON DELETE CASCADE,
                    PRIMARY KEY(run_id, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_demand_items_last_seen
                    ON demand_items(workspace_id, last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_demand_items_author
                    ON demand_items(workspace_id, author_name);
                """
            )
            row = conn.execute(
                "SELECT value FROM workspace_meta WHERE key = 'workspace_id'"
            ).fetchone()
            if row:
                return str(row["value"])
            workspace_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO workspace_meta(key, value) VALUES('workspace_id', ?)",
                (workspace_id,),
            )
            return workspace_id

    def save_search_results(
        self,
        *,
        query: str,
        region: str,
        city: str,
        mode: str,
        results: Iterable[dict[str, Any]],
    ) -> int:
        """Archive results and link them to this search. Returns unique rows linked."""
        items = [item for item in results if isinstance(item, dict)]
        run_id = str(uuid.uuid4())
        now = _utc_now()
        saved = 0
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO search_runs
                   (run_id, workspace_id, query, region, city, mode, result_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                (run_id, self.workspace_id, query.strip(), region.strip(), city.strip(),
                 mode.strip() or "posts", now),
            )
            for item in items:
                body = _value(item, "comment_text", "text")
                if not body:
                    continue
                kind = _normal_kind(_value(item, "kind", default=mode or "post"))
                key = _external_key(item, default_kind=kind)
                source_url = _value(item, "post_url", "url")
                conn.execute(
                    """INSERT INTO demand_items
                       (workspace_id, external_key, kind, body, interest, date_text,
                        source_url, profile_url, author_name, username, city,
                        first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(workspace_id, external_key) DO UPDATE SET
                         interest=excluded.interest,
                         date_text=excluded.date_text,
                         source_url=COALESCE(NULLIF(excluded.source_url, ''), demand_items.source_url),
                         profile_url=COALESCE(NULLIF(excluded.profile_url, ''), demand_items.profile_url),
                         author_name=COALESCE(NULLIF(excluded.author_name, ''), demand_items.author_name),
                         username=COALESCE(NULLIF(excluded.username, ''), demand_items.username),
                         city=COALESCE(NULLIF(excluded.city, ''), demand_items.city),
                         last_seen_at=excluded.last_seen_at""",
                    (
                        self.workspace_id, key, kind, body,
                        _value(item, "interest") or None,
                        _value(item, "date_text", "age") or None,
                        source_url,
                        _value(item, "profile_url"),
                        _value(item, "author_name"),
                        _value(item, "username"),
                        _value(item, "city", default=city),
                        now, now,
                    ),
                )
                row = conn.execute(
                    "SELECT item_id FROM demand_items WHERE workspace_id = ? AND external_key = ?",
                    (self.workspace_id, key),
                ).fetchone()
                if row:
                    linked = conn.execute(
                        "INSERT OR IGNORE INTO search_run_items(run_id, item_id) VALUES(?, ?)",
                        (run_id, int(row["item_id"])),
                    )
                    saved += max(0, linked.rowcount)
            conn.execute("UPDATE search_runs SET result_count = ? WHERE run_id = ?", (saved, run_id))
        return saved

    def count_items(self) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM demand_items WHERE workspace_id = ?",
                (self.workspace_id,),
            ).fetchone()
            return int(row["n"] if row else 0)

    def list_items(
        self,
        *,
        query: str = "",
        kind: str = "",
        city: str = "",
        run_id: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return filtered archive rows for the local archive window."""
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        where = ["d.workspace_id = ?"]
        params: list[Any] = [self.workspace_id]
        if query.strip():
            where.append("(d.body LIKE ? OR d.author_name LIKE ? OR d.username LIKE ? OR d.source_url LIKE ?)")
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        if kind.strip():
            where.append("d.kind = ?")
            params.append(kind.strip())
        if city.strip():
            where.append("d.city LIKE ?")
            params.append(f"%{city.strip()}%")
        if run_id.strip():
            where.append("EXISTS (SELECT 1 FROM search_run_items sri WHERE sri.item_id = d.item_id AND sri.run_id = ?)")
            params.append(run_id.strip())
        sql = (
            "SELECT d.item_id, d.kind, d.body, d.interest, d.date_text, d.source_url, "
            "d.profile_url, d.author_name, d.username, d.city, d.first_seen_at, d.last_seen_at "
            "FROM demand_items d WHERE " + " AND ".join(where) +
            " ORDER BY d.last_seen_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def count_filtered(
        self, *, query: str = "", kind: str = "", city: str = "", run_id: str = ""
    ) -> int:
        where = ["d.workspace_id = ?"]
        params: list[Any] = [self.workspace_id]
        if query.strip():
            where.append("(d.body LIKE ? OR d.author_name LIKE ? OR d.username LIKE ? OR d.source_url LIKE ?)")
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        if kind.strip():
            where.append("d.kind = ?")
            params.append(kind.strip())
        if city.strip():
            where.append("d.city LIKE ?")
            params.append(f"%{city.strip()}%")
        if run_id.strip():
            where.append("EXISTS (SELECT 1 FROM search_run_items sri WHERE sri.item_id = d.item_id AND sri.run_id = ?)")
            params.append(run_id.strip())
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM demand_items d WHERE " + " AND ".join(where),
                params,
            ).fetchone()
            return int(row["n"] if row else 0)

    def list_search_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT run_id, query, region, city, mode, result_count, created_at
                   FROM search_runs WHERE workspace_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (self.workspace_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_item(self, item_id: int) -> bool:
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM demand_items WHERE item_id = ? AND workspace_id = ?",
                (int(item_id), self.workspace_id),
            )
            return cur.rowcount > 0

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.list_items(limit=limit)
