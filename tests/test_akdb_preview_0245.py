"""The AKDB change review is read-only and describes conflicts precisely."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from artin_akdb import SharedAkdbStore, build_bundle, bundle_change_preview, bundle_delta
from artin_sentinel.akdb_shared import sentinel_domain_extensions


class AkdbPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "akdb.sqlite3"
        self.bundle = build_bundle(extensions=sentinel_domain_extensions())

    def test_preview_lists_identity_edit_and_conflict_without_writing(self):
        with SharedAkdbStore(self.db) as store:
            store.sync_catalog()
            for extension in sentinel_domain_extensions():
                store.sync_extension(extension)
            modified = copy.deepcopy(self.bundle)
            modified["records"][0]["revision"] += 1
            modified["records"][0]["model"] = "New model"
            modified["records"][1]["model"] = "Conflicting model"
            before = store.conn.total_changes
            preview = bundle_change_preview(store, modified)
            self.assertEqual(store.conn.total_changes, before)
            self.assertEqual([item["status"] for item in preview], ["updated", "conflict"])
            self.assertEqual(preview[0]["changed_fields"], ["model", "revision"])
            self.assertEqual(bundle_delta(store, modified)["conflicts"], 1)
            with self.assertRaisesRegex(ValueError, "same-revision conflicts"):
                store.apply_official_bundle(modified, release_revision=1)

    def test_preview_includes_extension_schema_change_as_conflict(self):
        with SharedAkdbStore(self.db) as store:
            store.sync_catalog()
            for extension in sentinel_domain_extensions():
                store.sync_extension(extension)
            modified = copy.deepcopy(self.bundle)
            modified["extensions"][0]["extension_schema"] = "artin-akdb-sentinel-next"
            changes = bundle_change_preview(store, modified)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["scope"], "extension")
            self.assertEqual(changes[0]["status"], "conflict")
            self.assertEqual(changes[0]["changed_fields"], ["extension_schema"])
            self.assertEqual(bundle_delta(store, modified)["extension_conflicts"], 1)

    def test_new_items_and_field_names_are_previewed_without_payload_values(self):
        with SharedAkdbStore(self.db) as store:
            preview = bundle_change_preview(store, self.bundle)
            self.assertEqual(len(preview), len(self.bundle["records"]) + len(self.bundle["extensions"]))
            self.assertTrue(all(item["status"] == "new" for item in preview))
            self.assertNotIn("payload_json", json.dumps(preview))
            self.assertEqual(store.record_count(), 0)


if __name__ == "__main__":
    unittest.main()
