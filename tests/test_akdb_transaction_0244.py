"""Release application must leave official knowledge coherent on failure."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artin_akdb import SharedAkdbStore, build_bundle
from artin_sentinel.akdb_shared import sentinel_domain_extensions


class AkdbTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "akdb.sqlite3"
        self.bundle = build_bundle(extensions=sentinel_domain_extensions())

    def test_failed_extension_write_rolls_back_core_and_release(self):
        modified = copy.deepcopy(self.bundle)
        modified["records"][0]["revision"] += 1
        modified["records"][0]["model"] = "REVISED"
        stable_id = modified["records"][0]["stable_id"]
        with SharedAkdbStore(self.db) as store:
            store.sync_catalog()
            original = store.conn.execute("SELECT model,revision FROM records WHERE stable_id=?", (stable_id,)).fetchone()
            with patch.object(store, "sync_extension", side_effect=RuntimeError("injected failure")):
                with self.assertRaisesRegex(RuntimeError, "injected failure"):
                    store.apply_official_bundle(modified, release_revision=1, bundle_sha256="a" * 64)
            current = store.conn.execute("SELECT model,revision FROM records WHERE stable_id=?", (stable_id,)).fetchone()
            self.assertEqual(tuple(current), tuple(original))
            self.assertEqual(store.official_release_state()["release_revision"], 0)

    def test_same_revision_conflict_keeps_release_unapplied(self):
        modified = copy.deepcopy(self.bundle)
        modified["records"][0]["model"] = "CONFLICT"
        with SharedAkdbStore(self.db) as store:
            store.sync_catalog()
            before = store.record_count()
            with self.assertRaisesRegex(ValueError, "same-revision conflicts"):
                store.apply_official_bundle(modified, release_revision=1, bundle_sha256="b" * 64)
            self.assertEqual(store.record_count(), before)
            self.assertEqual(store.official_release_state()["release_revision"], 0)

    def test_older_or_reused_revision_cannot_replace_official_knowledge(self):
        with SharedAkdbStore(self.db) as store:
            store.apply_official_bundle(self.bundle, release_revision=2, bundle_sha256="c" * 64)
            with self.assertRaisesRegex(ValueError, "older"):
                store.apply_official_bundle(self.bundle, release_revision=1, bundle_sha256="d" * 64)
            with self.assertRaisesRegex(ValueError, "different content"):
                store.apply_official_bundle(self.bundle, release_revision=2, bundle_sha256="d" * 64)
            self.assertEqual(store.official_release_state()["release_revision"], 2)
            self.assertEqual(store.official_release_state()["bundle_sha256"], "c" * 64)


if __name__ == "__main__":
    unittest.main()
