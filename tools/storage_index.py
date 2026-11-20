"""Persistent SQLite index for Builder storage measurements.

The index stores one row per *directory* (never per file) plus the JSON
snapshot that the storage page renders. Directory rows carry the identity
metadata used to decide whether a subtree may be reused and the aggregates
that make an instant cached page load possible.

Everything here is advisory. A missing, corrupt, oversized or future-versioned
database is discarded and rebuilt by a normal scan. Nothing in the index is
ever used to decide what may be deleted: cleanup re-validates every target on
the live filesystem.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 5
# A directory row is roughly 150 bytes. Refuse to load an index that would need
# more than this many rows and rebuild it rather than balloon the scan process.
MAX_NODES = 400_000
# root_id + rel + the 14 node columns + scanned_at.
NODE_COLUMNS = 14
PRUNE_AFTER_DAYS = 45

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    engine INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    complete INTEGER NOT NULL DEFAULT 0,
    last_scan_at REAL,
    duration_ms INTEGER,
    files INTEGER NOT NULL DEFAULT 0,
    dirs INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER NOT NULL DEFAULT 0,
    event_id INTEGER,
    event_valid INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dirs (
    root_id INTEGER NOT NULL,
    rel TEXT NOT NULL,
    ino INTEGER NOT NULL,
    dev INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    ctime_ns INTEGER NOT NULL,
    own_bytes INTEGER NOT NULL,
    own_files INTEGER NOT NULL,
    own_ipa INTEGER NOT NULL,
    multi_links INTEGER NOT NULL,
    sub_bytes INTEGER NOT NULL,
    sub_files INTEGER NOT NULL,
    sub_dirs INTEGER NOT NULL,
    sub_ipa INTEGER NOT NULL,
    sub_multi INTEGER NOT NULL,
    complete INTEGER NOT NULL DEFAULT 1,
    scanned_at REAL NOT NULL,
    PRIMARY KEY (root_id, rel)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS snapshots (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created REAL NOT NULL
);
"""


def default_index_path() -> Path:
    """Application data, never inside a storage root or a build product."""
    override = os.environ.get('MCFAO_STORAGE_INDEX')
    if override:
        return Path(override).expanduser()
    from storage_config import config_path

    return config_path().parent / 'storage-index.sqlite3'


class IndexUnavailable(RuntimeError):
    """The database cannot be opened; callers fall back to a plain scan."""


class StorageIndex:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_index_path()
        self._db: sqlite3.Connection | None = None

    # -- connection -----------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), timeout=8.0, isolation_level=None)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=NORMAL')
            db.execute('PRAGMA busy_timeout=8000')
            db.execute('PRAGMA temp_store=MEMORY')
            self._ensure(db)
            self._db = db
        except (OSError, sqlite3.Error) as error:
            self._db = None
            raise IndexUnavailable(str(error)) from error
        return self._db

    def _ensure(self, db: sqlite3.Connection) -> None:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            # Unknown or older layout: rebuild instead of migrating blind.
            for table in ('dirs', 'snapshots', 'roots', 'meta'):
                db.execute(f'DROP TABLE IF EXISTS {table}')
        db.executescript(DDL)
        if version != SCHEMA_VERSION:
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    def close(self) -> None:
        if self._db is not None:
            try:
                self._db.close()
            except sqlite3.Error:
                pass
            self._db = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exc):
        self.close()

    @contextmanager
    def write(self):
        db = self.connect()
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
        except BaseException:
            db.execute('ROLLBACK')
            raise
        db.execute('COMMIT')

    # -- roots ----------------------------------------------------------
    ROOT_COLUMNS = ('id', 'path', 'engine', 'status', 'error', 'complete', 'last_scan_at',
                    'duration_ms', 'files', 'dirs', 'bytes', 'event_id', 'event_valid')

    def root(self, path: str) -> dict | None:
        db = self.connect()
        row = db.execute(
            'SELECT id, path, engine, status, error, complete, last_scan_at, duration_ms, '
            'files, dirs, bytes, event_id, event_valid FROM roots WHERE path=?',
            (str(path),),
        ).fetchone()
        return dict(zip(self.ROOT_COLUMNS, row)) if row else None

    def upsert_root(self, path: str, **fields) -> int:
        db = self.connect()
        db.execute('INSERT OR IGNORE INTO roots(path) VALUES(?)', (str(path),))
        if fields:
            columns = ', '.join(f'{key}=?' for key in fields)
            db.execute(f'UPDATE roots SET {columns} WHERE path=?',
                       (*fields.values(), str(path)))
        return int(db.execute('SELECT id FROM roots WHERE path=?', (str(path),)).fetchone()[0])

    def roots(self) -> list[dict]:
        db = self.connect()
        return [self.root(row[0]) for row in db.execute('SELECT path FROM roots').fetchall()]

    # -- directory rows -------------------------------------------------
    def nodes(self, root_id: int) -> dict | None:
        """Return rel -> node tuple, or None when the index is too large to load."""
        db = self.connect()
        total = db.execute('SELECT COUNT(*) FROM dirs WHERE root_id=?', (root_id,)).fetchone()[0]
        if total > MAX_NODES:
            return None
        rows = db.execute(
            'SELECT rel, ino, dev, mtime_ns, ctime_ns, own_bytes, own_files, own_ipa, '
            'multi_links, sub_bytes, sub_files, sub_dirs, sub_ipa, sub_multi, complete '
            'FROM dirs WHERE root_id=?', (root_id,))
        return {row[0]: tuple(row[1:]) for row in rows}

    def replace_nodes(self, root_id: int, nodes: dict, previous: dict | None = None) -> int:
        """Persist the new node set, writing only rows that changed."""
        stamp = time.time()
        # A malformed row would abort the whole transaction, so drop it here
        # instead of failing a scan that is otherwise valid.
        nodes = {rel: tuple(node) for rel, node in nodes.items()
                 if len(node) == NODE_COLUMNS}
        insert = (
            'INSERT OR REPLACE INTO dirs(root_id, rel, ino, dev, mtime_ns, ctime_ns, '
            'own_bytes, own_files, own_ipa, multi_links, sub_bytes, sub_files, sub_dirs, '
            'sub_ipa, sub_multi, complete, scanned_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        )
        with self.write() as db:
            if previous is None:
                db.execute('DELETE FROM dirs WHERE root_id=?', (root_id,))
                db.executemany(insert, [(root_id, rel, *node, stamp)
                                         for rel, node in nodes.items()])
                return len(nodes)
            stale = [rel for rel in previous if rel not in nodes]
            if stale:
                db.executemany('DELETE FROM dirs WHERE root_id=? AND rel=?',
                               [(root_id, rel) for rel in stale])
            changed = [(root_id, rel, *node, stamp)
                       for rel, node in nodes.items()
                       if previous.get(rel) != tuple(node)]
            if changed:
                db.executemany(insert, changed)
            return len(changed) + len(stale)

    def invalidate(self, root_id: int, rels) -> int:
        """Forget every cached directory at or below each changed path."""
        removed = 0
        with self.write() as db:
            for rel in rels:
                if rel in ('', '.'):
                    db.execute('DELETE FROM dirs WHERE root_id=?', (root_id,))
                    removed += db.total_changes
                    continue
                # 'a/b' invalidates 'a/b' and 'a/b/...', but never 'a/bc'.
                db.execute('DELETE FROM dirs WHERE root_id=? AND (rel=? OR rel LIKE ?)',
                           (root_id, rel, rel.replace('%', '\\%').replace('_', '\\_') + '/%'))
                removed += db.total_changes
        return removed

    def drop(self, root_id: int) -> None:
        with self.write() as db:
            db.execute('DELETE FROM dirs WHERE root_id=?', (root_id,))

    # -- snapshots ------------------------------------------------------
    def snapshot(self, key: str) -> dict | None:
        db = self.connect()
        row = db.execute('SELECT payload, created FROM snapshots WHERE key=?', (key,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        payload['_cachedAt'] = row[1]
        return payload

    def save_snapshot(self, key: str, payload: dict) -> None:
        with self.write() as db:
            db.execute('INSERT OR REPLACE INTO snapshots(key, payload, created) VALUES(?,?,?)',
                       (key, json.dumps(payload, ensure_ascii=False), time.time()))

    # -- maintenance ----------------------------------------------------
    def prune(self, *, days: int = PRUNE_AFTER_DAYS) -> int:
        cutoff = time.time() - days * 86400
        removed = 0
        with self.write() as db:
            rows = db.execute('SELECT id FROM roots WHERE COALESCE(last_scan_at, 0) < ?',
                              (cutoff,)).fetchall()
            for (root_id,) in rows:
                db.execute('DELETE FROM dirs WHERE root_id=?', (root_id,))
                db.execute('DELETE FROM roots WHERE id=?', (root_id,))
                removed += 1
        return removed

    def stats(self) -> dict:
        db = self.connect()
        try:
            size = self.path.stat().st_size
        except OSError:
            size = 0
        return dict(
            path=str(self.path),
            roots=db.execute('SELECT COUNT(*) FROM roots').fetchone()[0],
            nodes=db.execute('SELECT COUNT(*) FROM dirs').fetchone()[0],
            snapshots=db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],
            bytes=size, schema=SCHEMA_VERSION)


def open_index(path: Path | None = None) -> StorageIndex | None:
    """Open the shared index, returning None when it cannot be used."""
    try:
        index = StorageIndex(path)
        index.connect()
        return index
    except (IndexUnavailable, sqlite3.Error, OSError):
        return None
