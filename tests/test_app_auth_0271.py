from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from artin_sentinel.app_auth import AppAuth


class AppAuthTest(unittest.TestCase):
    def test_create_verify_rotate_and_reject_corrupt_record(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "access.json"
            auth = AppAuth(path)
            self.assertFalse(auth.configured)
            with self.assertRaises(ValueError):
                auth.set_password("abc")
            auth.set_password("1234")
            self.assertTrue(auth.verify("1234"))
            auth.set_password("senha segura 1")
            self.assertTrue(auth.configured)
            self.assertTrue(auth.verify("senha segura 1"))
            self.assertFalse(auth.verify("senha errada"))
            self.assertNotIn("senha segura 1", path.read_text())
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            auth.set_password("senha segura 2")
            self.assertFalse(auth.verify("senha segura 1"))
            self.assertTrue(auth.verify("senha segura 2"))
            record = json.loads(path.read_text())
            record["algorithm"] = "unknown"
            path.write_text(json.dumps(record))
            self.assertFalse(auth.verify("senha segura 2"))
