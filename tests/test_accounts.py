import unittest
from accounts import hash_pin, verify_pin


class PinTests(unittest.TestCase):
    def test_accepts_correct_pin_and_rejects_wrong_pin(self):
        encoded = hash_pin('5729')
        self.assertTrue(verify_pin('5729', encoded))
        self.assertFalse(verify_pin('5730', encoded))
        self.assertNotIn('5729', encoded.split('$')[0])

    def test_hash_uses_unique_salt(self):
        self.assertNotEqual(hash_pin('5729'), hash_pin('5729'))

    def test_rejects_invalid_inputs_and_damaged_hashes(self):
        encoded = hash_pin('5729')
        for pin in (None, 5729, '', 'abcd', '５７２９', '12345'):
            self.assertFalse(verify_pin(pin, encoded))
        for damaged in (None, '', 'plain$00$00', 'scrypt$zz$ff'):
            self.assertFalse(verify_pin('5729', damaged))
