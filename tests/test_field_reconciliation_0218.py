from pathlib import Path
from types import SimpleNamespace

from artin_sentinel import __version__
from artin_sentinel.device_intelligence import device_visual_name
from artin_sentinel.db import Database
from artin_sentinel.domain import Device
from artin_sentinel.xm_dvrip import dvrip_ptz_command


def test_release_version_0218():
    assert __version__ == "0.2.89"


def test_itblue_horizontal_mapping_is_field_corrected():
    assert dvrip_ptz_command("left") == "DirectionRight"
    assert dvrip_ptz_command("right") == "DirectionLeft"
    assert dvrip_ptz_command("up-left") == "DirectionRightUp"
    assert dvrip_ptz_command("up-right") == "DirectionLeftUp"
    assert dvrip_ptz_command("down-left") == "DirectionRightDown"
    assert dvrip_ptz_command("down-right") == "DirectionLeftDown"
    assert dvrip_ptz_command("up") == "DirectionUp"
    assert dvrip_ptz_command("down") == "DirectionDown"


def test_visual_name_prefers_model_over_generic_discovery_name():
    row = {
        "name": "Hikvision", "manufacturer": "Hikvision", "model": "DS-7216HGHI-F1",
        "detected_manufacturer": "Hikvision", "detected_model": "DS-7216HGHI-F1", "ip": "192.0.2.10",
    }
    assert device_visual_name(row) == "DS-7216HGHI-F1"
    custom = dict(row, name="Portão")
    assert device_visual_name(custom) == "Portão"
    itblue = {
        "name": "SpeedDome Ball It-blue", "manufacturer": "IT-Blue", "model": "X3-WE2Q",
        "detected_manufacturer": "IT-Blue", "detected_model": "X3-WE2Q", "ip": "192.0.2.47",
    }
    assert device_visual_name(itblue) == "X3-WE2Q"


def test_available_only_channels_hide_stale_without_deleting_history(tmp_path: Path):
    db = Database(tmp_path / "channels.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, name="IT-Blue", ip="192.0.2.47"))
    first = [
        SimpleNamespace(channel=1, name="Lente PTZ", rtsp_url="rtsp://x/1", available=True, detail="ok"),
        SimpleNamespace(channel=2, name="Câmera 02", rtsp_url="rtsp://x/2", available=True, detail="ok"),
        SimpleNamespace(channel=3, name="Câmera 03", rtsp_url="rtsp://x/3", available=True, detail="ok"),
    ]
    db.replace_recorder_channels(did, first)
    db.replace_recorder_channels(did, [first[0]])
    assert len(db.list_recorder_channels(did)) == 3
    current = db.list_recorder_channels(did, available_only=True)
    assert [row["channel_no"] for row in current] == [1]
    db.close()


def test_live_ui_uses_native_audio_icon_and_persistent_ptz_status():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self.audio_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))' in source
    assert 'self.audio_button.setText("🔊")' not in source
    assert 'text = "PTZ disponível"' in source
    assert 'self.ptz_status_label.setText("PTZ disponível")' in source
    assert 'self.db.list_recorder_channels(device_id)' in source


def test_itblue_signature_uses_central_crop_to_avoid_overlays():
    source = Path("artin_sentinel/ip_camera.py").read_text(encoding="utf-8")
    assert "crop=trunc(iw*0.72):trunc(ih*0.62):trunc(iw*0.14):trunc(ih*0.19)" in source
    assert "logical_with_video" in source


def test_shared_akdb_revisions_advance_for_field_confirmed_x3():
    from artin_akdb import record_by_legacy_key
    from artin_sentinel.akdb_shared import sentinel_domain_extensions
    core = record_by_legacy_key("it-blue-x3-we2q")
    assert core is not None and core.revision >= 8
    ext = next(e for e in sentinel_domain_extensions() if e.stable_id == core.stable_id)
    assert ext.revision >= 7


def test_operational_audio_does_not_claim_unvalidated_talkback():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert '"xm-dvrip-g711a-experimental"' in source
    assert '"intelbras-http-postaudio-experimental"' in source
    assert 'known_mode == "bidirectional"' in source
    assert 'scope_ok = channel_matches_capability_scope(channel, talkback_scope)' in source
    assert 'Escuta • retorno pendente' in source
    assert 'device_visual_name(device)' in source


def test_shared_akdb_rev2_upgrades_rev1_without_conflict(tmp_path):
    from dataclasses import replace
    from artin_akdb import SharedAkdbStore, record_by_legacy_key
    from artin_sentinel.akdb_shared import sentinel_domain_extensions

    current = record_by_legacy_key("it-blue-x3-we2q")
    assert current is not None
    old = replace(
        current, revision=1, validation_status="field-identified",
        protocols=("rtsp", "onvif-candidate", "xm-dvrip-34567-candidate"),
        capabilities=("network-video", "ptz", "zoom", "multi-view", "bidirectional-audio-candidate"),
    )
    ext_current = next(e for e in sentinel_domain_extensions() if e.stable_id == current.stable_id)
    ext_old = replace(ext_current, revision=1, payload={**dict(ext_current.payload), "ptz_mode": "onvif-candidate"})

    db_path = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(db_path) as store:
        assert store.sync_catalog([old]) == 1
        store.sync_extension(ext_old)
        assert store.sync_catalog([current]) == 1
        store.sync_extension(ext_current)
        row = store.conn.execute("SELECT revision,validation_status FROM records WHERE stable_id=?", (current.stable_id,)).fetchone()
        ext = store.conn.execute("SELECT revision,payload_json FROM domain_extensions WHERE stable_id=? AND domain='sentinel'", (current.stable_id,)).fetchone()
        assert int(row["revision"]) == 9
        assert row["validation_status"] == "field-validated"
        assert int(ext["revision"]) == 9
        assert store.conflict_count() == 0
