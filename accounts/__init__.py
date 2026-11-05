"""PIN hashing for the temporary development profile, not a login endpoint."""
import hashlib
import hmac
import secrets


def hash_pin(pin):
    if not isinstance(pin, str) or len(pin) != 4 or any(c not in '0123456789' for c in pin):
        raise ValueError('PIN must contain four digits')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1)
    return 'scrypt$' + salt.hex() + '$' + digest.hex()


def verify_pin(pin, encoded):
    if not isinstance(pin, str) or len(pin) != 4 or any(c not in '0123456789' for c in pin):
        return False
    try:
        algorithm, salt_hex, digest_hex = encoded.split('$')
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if algorithm != 'scrypt' or len(salt) != 16 or len(expected) != 64:
            return False
        actual = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False
