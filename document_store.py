"""Local document identity, retained originals, and durable job history."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class DocumentStore:
    """One local writer at a time; the OS releases locks after a crash."""

    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()

    def __enter__(self):
        self.base.mkdir(parents=True, exist_ok=True)
        self.lock = (self.base / 'pipeline.lock').open('a+b')
        self.lock.seek(0, os.SEEK_END)
        if self.lock.tell() == 0:
            self.lock.write(b'0')
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            raise RuntimeError('Another pipeline process is using this data directory') from exc
        try:
            for folder in ('originals', 'landing', 'processed'):
                (self.base / folder).mkdir(exist_ok=True)
            self.db = sqlite3.connect(self.base / 'manifest.sqlite3')
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys = ON')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    suffix TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    output_dir TEXT,
                    last_error TEXT,
                    UNIQUE(sha256, suffix)
                );
                CREATE TABLE IF NOT EXISTS sources (
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    source_path TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY(document_id, source_path)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    detail TEXT
                );
            ''')
            return self
        except BaseException:
            if hasattr(self, 'db'):
                self.db.close()
            self.lock.close()
            raise

    def __exit__(self, *args):
        self.db.close()
        self.lock.close()

    def get(self, document_id):
        return self.db.execute('SELECT * FROM documents WHERE document_id=?',
                               (document_id,)).fetchone()

    def _event(self, document_id, status, detail=None):
        row = self.get(document_id)
        self.db.execute('INSERT INTO events(document_id,timestamp,status,attempt,detail) VALUES(?,?,?,?,?)',
                        (document_id, now(), status, row['attempts'], detail))

    def register(self, source):
        """Archive a stable snapshot before committing its identity; never alter source."""
        source = Path(source).resolve()
        suffix = source.suffix.lower()
        if suffix not in ('.pdf', '.csv'):
            raise ValueError(f'Unsupported document type: {source.name}')
        before = source.stat()
        fd, temporary = tempfile.mkstemp(prefix='.intake-', dir=self.base / 'originals')
        temporary = Path(temporary)
        try:
            digest = hashlib.sha256()
            with os.fdopen(fd, 'wb') as archived, source.open('rb') as incoming:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                    archived.write(chunk)
                    digest.update(chunk)
                archived.flush()
                os.fsync(archived.fileno())
            after = source.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size, after.st_mtime_ns, after.st_ino):
                raise RuntimeError(f'Source changed during intake: {source.name}; retry after upload finishes')
            sha256 = digest.hexdigest()
            row = self.db.execute('SELECT * FROM documents WHERE sha256=? AND suffix=?',
                                  (sha256, suffix)).fetchone()
            created = row is None
            document_id = uuid.uuid4().hex if created else row['document_id']
            if created:
                original = self.base / 'originals' / document_id / ('original' + suffix)
                original.parent.mkdir()
                os.replace(temporary, original)
            with self.db:
                if created:
                    self.db.execute('''INSERT INTO documents
                        (document_id,sha256,suffix,original_name,original_path,size_bytes,created_at,status)
                        VALUES(?,?,?,?,?,?,?,?)''',
                        (document_id, sha256, suffix, source.name,
                         str(original.relative_to(self.base)), after.st_size, now(), 'pending'))
                    self._event(document_id, 'pending', 'Original archived')
                timestamp = now()
                self.db.execute('''INSERT INTO sources VALUES(?,?,?,?)
                    ON CONFLICT(document_id,source_path) DO UPDATE SET last_seen=excluded.last_seen''',
                    (document_id, str(source), timestamp, timestamp))
            return document_id, created
        finally:
            temporary.unlink(missing_ok=True)

    def recover(self, retry_failed=False):
        """The process lock ensures processing jobs belong to an interrupted run."""
        statuses = ('processing', 'failed') if retry_failed else ('processing',)
        for status in statuses:
            rows = self.db.execute('SELECT document_id FROM documents WHERE status=?', (status,)).fetchall()
            for row in rows:
                with self.db:
                    self.db.execute("UPDATE documents SET status='pending' WHERE document_id=?",
                                    (row['document_id'],))
                    self._event(row['document_id'], 'pending',
                                'Explicit failed-job retry' if status == 'failed' else 'Recovered interrupted attempt')

    def pending(self):
        return self.db.execute("SELECT * FROM documents WHERE status='pending' ORDER BY created_at").fetchall()

    def start(self, document_id):
        with self.db:
            changed = self.db.execute("""UPDATE documents SET status='processing',
                attempts=attempts+1, last_error=NULL WHERE document_id=? AND status='pending'""",
                (document_id,)).rowcount
            if changed != 1:
                raise ValueError('Only pending documents can start an attempt')
            self._event(document_id, 'processing')
        return self.get(document_id)

    def stage(self, document_id):
        row = self.get(document_id)
        original = self.base / row['original_path']
        if fingerprint(original) != row['sha256']:
            raise ValueError('Archived original failed SHA-256 integrity check')
        folder = self.base / 'landing' / document_id
        folder.mkdir(exist_ok=True)
        path = folder / ('document' + row['suffix'])
        temporary = folder / 'document.tmp'
        shutil.copyfile(original, temporary)
        if fingerprint(temporary) != row['sha256']:
            raise ValueError('Landing copy failed SHA-256 integrity check')
        os.replace(temporary, path)
        return path

    def finish(self, document_id, output_dir=None, error=None):
        status = 'failed' if error is not None else 'completed'
        with self.db:
            self.db.execute('UPDATE documents SET status=?,output_dir=?,last_error=? WHERE document_id=?',
                            (status, output_dir, error, document_id))
            self._event(document_id, status, error or output_dir)

    @contextmanager
    def export_attempt(self, document_id):
        """Publish outputs together; manifest completion is the success marker."""
        row = self.get(document_id)
        parent = self.base / 'processed' / document_id
        parent.mkdir(exist_ok=True)
        final = parent / f"attempt-{row['attempts']:04d}"
        temporary = Path(tempfile.mkdtemp(prefix='.export-', dir=parent))
        try:
            yield temporary
            (temporary / 'document.json').write_text(json.dumps({
                'document_id': document_id, 'sha256': row['sha256'],
                'original_name': row['original_name'], 'attempt': row['attempts'],
                'exported_at': now(),
            }, indent=2), encoding='utf-8')
            for path in temporary.iterdir():
                # Windows requires a writable handle for FlushFileBuffers/fsync.
                with path.open('r+b') as stream:
                    os.fsync(stream.fileno())
            os.replace(temporary, final)
            self.finish(document_id, output_dir=str(final.relative_to(self.base)))
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
