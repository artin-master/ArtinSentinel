from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from artin_akdb import KnowledgeRecord, SharedAkdbStore
from artin_sentinel.akdb_runtime import effective_core_records
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.fingerprint import identify_device
from artin_sentinel.lan_discovery import HostObservation, probe_host


class DiscoveryAkdbTest(TestCase):
    def test_network_brand_or_web_port_is_not_cctv(self):
        router = HostObservation("192.0.2.1", manufacturer="Intelbras", model="Roteador",
                                 open_ports=[80, 8080], evidence=["assinatura HTTP compatível com intelbras"])
        self.assertFalse(router.looks_like_cctv)
        with patch("artin_sentinel.lan_discovery._tcp_open", side_effect=lambda ip, port: port == 554), \
             patch("artin_sentinel.lan_discovery._probe_onvif_endpoint", return_value=""):
            candidate = probe_host("192.0.2.2")
        self.assertTrue(candidate.looks_like_cctv)
        self.assertEqual(candidate.kind, DeviceKind.UNKNOWN)

    def test_new_shared_record_can_identify_model_without_packaged_profile(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "akdb.sqlite3"
            with SharedAkdbStore(path) as store:
                store.sync_catalog()
                store.sync_catalog(records=(KnowledgeRecord(
                    stable_id="artin.device.example-camera-0279", manufacturer="Example",
                    model="XC 279", canonical_type="camera-fixed", domains=("sentinel", "netlens"),
                    validation_status="field-validated", revision=1,
                ),), core_revision=99)
            with patch("artin_sentinel.akdb_runtime.default_store_path", return_value=path):
                self.assertTrue(any(r.stable_id == "artin.device.example-camera-0279" for r in effective_core_records()))
                decision = identify_device(Device(name="XC 279", manufacturer="Example", model="XC 279"))
                self.assertEqual(decision.canonical_type, "camera-fixed")
                self.assertTrue(decision.auto_applied)
