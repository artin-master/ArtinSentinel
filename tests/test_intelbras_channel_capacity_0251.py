from types import SimpleNamespace

from artin_sentinel.akdb import (
    best_profile, recorder_scan_capacity_for_device, reconcile_operational_profile_key,
)
from artin_sentinel.recorder import RtspProbeReport, scan_intelbras_channels


def test_vendor_only_evidence_does_not_assign_five_channel_mhdx_profile():
    candidate = best_profile(text="Intelbras", manufacturer="Intelbras", ports=(80, 554, 37777))
    assert candidate is None or candidate[1].key != "intelbras-mhdx"
    for model, expected in (("NVD 1416", "intelbras-nvd-1416"),
                            ("NVD 1516", "intelbras-nvd-1516"),
                            ("MHDX 1216", "intelbras-mhdx-1216"),
                            ("MHDX 1004", "intelbras-mhdx")):
        matched = best_profile(text=f"Intelbras {model}", manufacturer="Intelbras",
                               ports=(80, 554, 37777))
        assert matched and matched[1].key == expected
        assert reconcile_operational_profile_key(
            profile_key="intelbras-mhdx", provider="intelbras", identity_text=f"Intelbras {model}"
        ) == expected


def test_capacity_uses_model_or_manual_selection_before_stale_five_channel_profile():
    old = "intelbras-mhdx"
    assert recorder_scan_capacity_for_device(provider="intelbras", profile_key=old, model="MHDX 1004") == 5
    for name in ("NVD 1416", "NVD 1516", "MHDX 1216", "Intelbras"):
        assert recorder_scan_capacity_for_device(provider="intelbras", profile_key=old, name=name) == 16
    assert recorder_scan_capacity_for_device(provider="intelbras", profile_key=old,
                                             model="MHDX 1004", saved_limit=16) == 16
    assert recorder_scan_capacity_for_device(provider="intelbras", profile_key=old,
                                             model="NVD 1516", name="Antigo MHDX 1004") == 16


def test_sixteen_selected_positions_are_kept_even_when_rtsp_has_no_video(monkeypatch):
    from artin_sentinel import recorder
    inventory = SimpleNamespace(channels=[SimpleNamespace(channel_id=1, name="Entrada")],
                                ok=True, authenticated=True, detail="CGI OK")
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *_a, **_k: inventory)
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *_a, **_k: (1, 0, "RTSP", "rtsp://seed"))
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", lambda *_a, **_k:
                        RtspProbeReport(False, 404, "sem mídia", first_status=404))
    result = scan_intelbras_channels("192.0.2.8", "admin", "password", max_channels=16,
                                    channel_layout="nvr")
    assert [channel.channel for channel in result] == list(range(1, 17))
    assert not any(channel.available for channel in result)
    assert {channel.channel_kind for channel in result} == {"ip"}


def test_installer_separates_sdk_and_checks_regular_media_dependencies():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "install.sh").read_text()
    assert "if required_missing; then" in source
    assert "p+=(openssh-clients)" in source and "p+=(openssh-client)" in source
    assert "install_intelbras_netsdk.py" not in source


def test_akdb_revision_upgrade_does_not_conflict_on_unchanged_records(tmp_path):
    from artin_akdb import CORE_RECORDS, CORE_REVISION, SharedAkdbStore
    with SharedAkdbStore(tmp_path / "upgrade.sqlite3") as store:
        assert store.sync_catalog([CORE_RECORDS[0]], core_revision=CORE_REVISION - 1) == 1
        assert store.sync_catalog([CORE_RECORDS[0]], core_revision=CORE_REVISION) == 1
        assert store.conflict_count() == 0
        assert store.sync_catalog([CORE_RECORDS[0]], core_revision=CORE_REVISION) == 0
