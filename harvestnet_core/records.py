"""Transactional JSON records and append-only events; SQLite locally, Postgres live.

All writes in one operation share a transaction. Events contain no contact addresses.
"""
from contextlib import contextmanager
import json
import sqlite3
import threading


class NotFound(KeyError):
    """No stored record of this kind and ID. Still a ``KeyError`` for existing callers."""


class Records:
    def __init__(self, database=":memory:"):
        self.lock = threading.RLock()
        self.email_outbox_enabled = False
        self._transaction_depth = 0
        self.postgres = database.startswith(("postgres://", "postgresql://"))
        if self.postgres:
            import psycopg
            self.db = psycopg.connect(database, autocommit=True)
        else:
            self.db = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
            self.db.execute("PRAGMA busy_timeout=10000")
            self.db.execute("PRAGMA journal_mode=WAL")
        self.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
        sequence = "BIGSERIAL" if self.postgres else "INTEGER"
        self.execute(f"CREATE TABLE IF NOT EXISTS events (sequence {sequence} PRIMARY KEY, run_id TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        return self.db.execute(sql, params)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.execute("BEGIN IMMEDIATE" if not self.postgres else "BEGIN")
            self._transaction_depth += 1
            try:
                if self.postgres:
                    # Serialize reservations across API processes, not just threads.
                    self.execute("SELECT pg_advisory_xact_lock(726194021)")
                yield self
                self.execute("COMMIT")
            except BaseException:
                self.execute("ROLLBACK")
                raise
            finally:
                self._transaction_depth -= 1

    def enable_email_outbox(self):
        """Queue only future pickup events; enabling never replays historical events."""
        with self.lock:
            self.email_outbox_enabled = True

    def put(self, kind, id, data):
        self.execute("INSERT INTO records(kind,id,data) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, id, json.dumps(data, allow_nan=False)))

    def get(self, kind, id):
        row = self.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        if row is None:
            raise NotFound(id)
        return json.loads(row[0])

    def all(self, kind):
        return [json.loads(row[0]) for row in self.execute("SELECT data FROM records WHERE kind=? ORDER BY id", (kind,)).fetchall()]

    def delete(self, kind, id):
        self.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, id))

    def event(self, run_id, at, kind, data):
        notice = None
        if self.email_outbox_enabled and data.get('pickup_id'):
            if kind == 'pickup_notice':
                notice = {'pickup_id': data['pickup_id'],
                          'kind': 'pickup_changed' if data.get('moved_from_food_bank_id') else 'pickup_ready',
                          'version': data.get('version')}
            elif kind == 'pickup_released' and data.get('source') == 'household':
                notice = {'pickup_id': data['pickup_id'], 'kind': 'pickup_released', 'version': None}
        with self.lock:
            # The event and outbox entry must commit together, including callers that do
            # not already own a transaction. No contact address is kept in either record.
            if notice and not self._transaction_depth:
                with self.transaction():
                    self._insert_event(run_id, at, kind, data, notice)
            else:
                self._insert_event(run_id, at, kind, data, notice)

    def _insert_event(self, run_id, at, kind, data, notice):
        sql = "INSERT INTO events(run_id,at,kind,data) VALUES(?,?,?,?)"
        if notice and self.postgres:
            sql += " RETURNING sequence"
        cursor = self.execute(sql, (run_id, at, kind, json.dumps(data, allow_nan=False)))
        if notice:
            sequence = cursor.fetchone()[0] if self.postgres else cursor.lastrowid
            self.put('email_outbox', str(sequence), {
                'event_sequence': sequence, **notice, 'status': 'pending'})

    def events(self, run_id):
        return [{"sequence": r[0], "at": r[1], "kind": r[2], "data": json.loads(r[3])} for r in self.execute("SELECT sequence,at,kind,data FROM events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()]

    def events_of_kind(self, kind):
        return [{"sequence": r[0], "run_id": r[1], "at": r[2], "data": json.loads(r[3])} for r in self.execute("SELECT sequence,run_id,at,data FROM events WHERE kind=? ORDER BY sequence", (kind,)).fetchall()]

    def replace_event_data(self, sequence, data):
        """Only for privacy purges: an expired household's details are removed, the counts kept."""
        self.execute("UPDATE events SET data=? WHERE sequence=?", (json.dumps(data, allow_nan=False), sequence))

    def close(self):
        self.db.close()
