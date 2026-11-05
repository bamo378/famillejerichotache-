import os
import unittest
from unittest.mock import patch
from notifications import notify_parent, DeliveryError


class NotificationTests(unittest.TestCase):
    @patch.dict(os.environ, {'SITE_URL': 'https://family.example'}, clear=True)
    @patch('notifications.request.urlopen')
    def test_preview_never_sends(self, send):
        result = notify_parent('task/123')
        self.assertEqual(result['status'], 'preview')
        self.assertIn('/parents/taches/task%2F123', result['message'])
        send.assert_not_called()

    @patch.dict(os.environ, {'SITE_URL': 'https://family.example'}, clear=True)
    @patch('notifications.request.urlopen')
    def test_missing_credentials_prevents_send(self, send):
        with self.assertRaises(DeliveryError):
            notify_parent('123', live=True)
        send.assert_not_called()

    @patch.dict(os.environ, {'SITE_URL': 'http://family.example'}, clear=True)
    def test_requires_https(self):
        with self.assertRaises(ValueError):
            notify_parent('123')

    @patch.dict(os.environ, {'SITE_URL': 'https://family.example', 'TWILIO_ACCOUNT_SID': 'AC' + 'a'*32,
                            'TWILIO_AUTH_TOKEN': 'test-only', 'SMS_FROM': '+41790000000',
                            'PARENT_PHONE': '+41790000001'}, clear=True)
    @patch('notifications.request.urlopen')
    def test_provider_submission(self, send):
        import io
        send.return_value.__enter__.return_value = io.BytesIO(b'{"sid":"SMtest","status":"queued"}')
        self.assertEqual(notify_parent('123', live=True)['status'], 'queued')
        req = send.call_args.args[0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertIn('To=%2B41790000001', req.data.decode())
        self.assertNotIn('photo', req.data.decode())


if __name__ == '__main__':
    unittest.main()
