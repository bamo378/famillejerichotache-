"""Server-side SMS delivery. Never expose provider credentials to a browser."""
import base64
import json
import os
from urllib import parse, request


class DeliveryError(RuntimeError):
    pass


def notify_parent(task_id, *, live=False):
    """Send only to the configured parent; default mode never contacts a provider."""
    site = os.environ.get('SITE_URL', '').rstrip('/')
    if not site.startswith('https://'):
        raise ValueError('SITE_URL must use HTTPS')
    link = site + '/parents/taches/' + parse.quote(str(task_id), safe='')
    message = 'Une tâche attend votre validation. Consultez votre espace familial : ' + link
    if not live:
        return {'status': 'preview', 'message': message}
    names = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SMS_FROM', 'PARENT_PHONE')
    if any(not os.environ.get(name) for name in names):
        raise DeliveryError('SMS configuration is incomplete')
    sid, token, sender, recipient = (os.environ[name] for name in names)
    for phone in (sender, recipient):
        if not phone.startswith('+') or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
            raise ValueError('Phone numbers must use international format')
    if not sid.startswith('AC') or len(sid) != 34 or not all(c in '0123456789abcdefABCDEF' for c in sid[2:]):
        raise ValueError('Invalid Twilio account SID')
    payload = parse.urlencode({'From': sender, 'To': recipient, 'Body': message}).encode()
    auth = base64.b64encode((sid + ':' + token).encode()).decode()
    req = request.Request('https://api.twilio.com/2010-04-01/Accounts/' + sid + '/Messages.json',
                          data=payload, headers={'Authorization': 'Basic ' + auth})
    try:
        with request.urlopen(req, timeout=15) as response:
            result = json.load(response)
    except Exception:
        # Provider errors may contain phone numbers or request details.
        raise DeliveryError('SMS submission failed; check provider delivery logs') from None
    return {'status': result.get('status', 'submitted'), 'id': result.get('sid')}
