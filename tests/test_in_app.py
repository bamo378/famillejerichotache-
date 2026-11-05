import json
import tempfile
import unittest
from pathlib import Path
from notifications.in_app import Inbox


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'inbox.sqlite3'
        self.inbox = Inbox(self.path)

    def publish(self, **overrides):
        args = dict(recipient_id='parent', event_id='submission-1', kind='task_submitted', task_id='task-1')
        args.update(overrides)
        return self.inbox.publish(**args)

    def test_persists_without_duplicate_on_retry(self):
        self.assertTrue(self.publish())
        self.assertFalse(self.publish())
        self.assertEqual(len(Inbox(self.path).list_for('parent')), 1)

    def test_recipient_isolation_and_read_status(self):
        self.publish()
        self.assertEqual(self.inbox.list_for('alice'), [])
        row = self.inbox.list_for('parent')[0]
        self.assertFalse(self.inbox.mark_read('alice', row['id']))
        self.assertEqual(len(self.inbox.list_for('parent', unread_only=True)), 1)
        self.assertTrue(self.inbox.mark_read('parent', row['id']))
        self.assertEqual(self.inbox.list_for('parent', unread_only=True), [])

    def test_children_can_receive_separate_notifications(self):
        for child in ['alice', 'anaelle', 'tiziano']:
            self.publish(recipient_id=child, kind='contest_created')
            self.assertEqual(len(self.inbox.list_for(child)), 1)

    def test_invalid_events_are_rejected(self):
        with self.assertRaises(ValueError):
            self.publish(kind='unknown')
        with self.assertRaises(ValueError):
            self.publish(recipient_id='')

    def test_dishwasher_tasks_are_daily_and_sms_disabled(self):
        config = json.loads((Path(__file__).resolve().parents[1] / 'config/tasks.json').read_text())
        tasks = {task['id']: task for task in config['tasks']}
        for identifier in ('vider-lave-vaisselle', 'remplir-lave-vaisselle'):
            self.assertEqual(tasks[identifier]['frequency'], 'daily')
        self.assertFalse(config['sms_enabled'])
        self.assertEqual(config['notification_channel'], 'in_app')
