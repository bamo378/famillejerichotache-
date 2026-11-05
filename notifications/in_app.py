"""Free, persistent family inbox. Call from an authenticated application server.

recipient_id must always come from the authenticated session, never a request's
unverified profile selection. This storage module is not a public HTTP endpoint.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone


class Inbox:
    def __init__(self, database):
        self.database = str(database)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY,
                recipient_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                task_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT,
                UNIQUE(recipient_id, event_id)
            )''')

    def publish(self, *, recipient_id, event_id, kind, task_id):
        messages = {
            'task_assigned': 'Une nouvelle tâche vous attend.',
            'task_submitted': 'Une tâche terminée attend votre validation et sa photo est disponible dans le site.',
            'task_approved': 'Une tâche a été validée : vos points ont été ajoutés.',
            'contest_created': 'Un nouveau défi familial est disponible.',
        }
        if kind not in messages:
            raise ValueError('Unknown notification kind')
        if not all(isinstance(v, str) and v.strip() for v in (recipient_id, event_id, task_id)):
            raise ValueError('Recipient, event and task identifiers are required')
        with closing(sqlite3.connect(self.database)) as db, db:
            cursor = db.execute('''INSERT INTO notifications
                (recipient_id,event_id,kind,task_id,message,created_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(recipient_id,event_id) DO NOTHING''',
                (recipient_id, event_id, kind, task_id, messages[kind], datetime.now(timezone.utc).isoformat()))
            return cursor.rowcount == 1

    def list_for(self, recipient_id, *, unread_only=False):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('''SELECT id,kind,task_id,message,created_at,read_at
                FROM notifications WHERE recipient_id=?'''
                + (' AND read_at IS NULL' if unread_only else '')
                + ' ORDER BY id DESC LIMIT 100', (recipient_id,))
            return [dict(row) for row in rows]

    def mark_read(self, recipient_id, notification_id):
        with closing(sqlite3.connect(self.database)) as db, db:
            cursor = db.execute('''UPDATE notifications SET read_at=?
                WHERE id=? AND recipient_id=? AND read_at IS NULL''',
                (datetime.now(timezone.utc).isoformat(), notification_id, recipient_id))
            return cursor.rowcount == 1
