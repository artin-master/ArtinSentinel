from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from artin_akdb import DomainExtension, SharedAkdbStore, record_by_legacy_key
from artin_sentinel.akdb import capability_map, recorder_scan_capacity_for_device


class SharedAkdbRuntimeTest(TestCase):
    def test_newer_official_extension_drives_model_capacity_but_manual_wins(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "akdb.sqlite3"
            core = record_by_legacy_key("intelbras-nvd-1416")
            with SharedAkdbStore(path) as store:
                store.sync_catalog()
                store.sync_extension(DomainExtension(core.stable_id, "sentinel", "artin-akdb-sentinel-v2", 2,
                                                     {"max_total_channels": 16}))
            with patch("artin_sentinel.akdb.default_store_path", return_value=path):
                self.assertEqual(capability_map(profile_key="intelbras-nvd-1416")["max_total_channels"], 16)
                with SharedAkdbStore(path) as store:
                    store.sync_extension(DomainExtension(core.stable_id, "sentinel", "artin-akdb-sentinel-v2", 3,
                                                         {"max_total_channels": 24}))
                self.assertEqual(capability_map(profile_key="intelbras-nvd-1416")["max_total_channels"], 24)
                self.assertEqual(recorder_scan_capacity_for_device(
                    provider="intelbras", profile_key="intelbras-nvd-1416", model="NVD 1416"), 24)
                self.assertEqual(recorder_scan_capacity_for_device(
                    provider="intelbras", profile_key="intelbras-nvd-1416", model="NVD 1416",
                    saved_limit=12, saved_source="manual"), 12)
