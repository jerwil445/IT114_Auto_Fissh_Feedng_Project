"""Create PostgreSQL tables and optionally import an existing SQLite database."""
import argparse
import os
import sqlite3
from pathlib import Path

from aquafeed import DEFAULTS
from database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', action='store_true', help='Create the target PostgreSQL database if absent')
    parser.add_argument('--import-sqlite', type=Path, help='Import settings, history, and execution records into an unused database')
    args = parser.parse_args()
    url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/aquafeed')
    target = Database(url)
    if not target.postgres:
        parser.error('DATABASE_URL must be a PostgreSQL connection URL.')
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    if args.create:
        options = conninfo_to_dict(url)
        name = options.get('dbname', 'aquafeed')
        options['dbname'] = 'postgres'
        with psycopg.connect(**options, autocommit=True, connect_timeout=5) as admin:
            if not admin.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    target.initialize(DEFAULTS)
    if args.import_sqlite:
        source_path = args.import_sqlite.resolve(strict=True)
        source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)
        try:
            settings = source.execute('SELECT value FROM settings WHERE id=1').fetchone()
            events = source.execute('SELECT id,timestamp,kind,trigger,portion,status,message FROM events ORDER BY id').fetchall()
            executions = source.execute('SELECT key FROM executions').fetchall()
            with target.connect() as db:
                db.execute('LOCK TABLE settings, events, executions IN EXCLUSIVE MODE')
                if db.execute('SELECT count(*) AS count FROM events').fetchone()['count'] or db.execute('SELECT count(*) AS count FROM executions').fetchone()['count']:
                    raise RuntimeError('Import requires a database without events or executions; existing data was not overwritten.')
                import json
                if json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()['value']) != DEFAULTS:
                    raise RuntimeError('Target settings have been changed; import refused to avoid overwriting them.')
                if settings:
                    db.execute('UPDATE settings SET value=? WHERE id=1', settings)
                for event in events:
                    db.execute('INSERT INTO events(id,timestamp,kind,trigger,portion,status,message) VALUES(?,?,?,?,?,?,?)', event)
                for execution in executions:
                    db.execute('INSERT INTO executions(key) VALUES(?)', execution)
                db.execute("SELECT setval(pg_get_serial_sequence('events','id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM events")
            print(f'Imported {len(events)} events and {len(executions)} scheduled execution records. SQLite source unchanged.')
        finally:
            source.close()
    print('PostgreSQL database is ready.')


if __name__ == '__main__':
    main()
