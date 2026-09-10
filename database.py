"""PostgreSQL persistence; explicit SQLite paths support tests and legacy imports."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Connection:
    def __init__(self, connection, postgres):
        self.connection = connection
        self.postgres = postgres

    def execute(self, query, parameters=()):
        if self.postgres:
            query = query.replace('?', '%s')
        return self.connection.execute(query, parameters)


class Database:
    def __init__(self, location):
        self.location = str(location)
        self.postgres = self.location.startswith(('postgresql://', 'postgres://'))

    @contextmanager
    def connect(self):
        if self.postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError('Install requirements.txt to enable PostgreSQL (psycopg).') from exc
            connection = psycopg.connect(self.location, connect_timeout=5, row_factory=dict_row)
        else:
            connection = sqlite3.connect(self.location, timeout=10)
            connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield Connection(connection, self.postgres)
        finally:
            connection.close()

    def initialize(self, defaults):
        with self.connect() as db:
            if self.postgres:
                schema = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
                for statement in schema.split(';'):
                    if statement.strip():
                        db.execute(statement)
            else:
                db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, kind TEXT NOT NULL, trigger TEXT, portion TEXT, status TEXT NOT NULL, message TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS executions (key TEXT PRIMARY KEY)')
            db.execute('INSERT INTO settings(id, value) VALUES(1, ?) ON CONFLICT (id) DO NOTHING', (json.dumps(defaults),))
