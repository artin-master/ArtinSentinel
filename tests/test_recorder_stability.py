from pathlib import Path
from threading import Event

import pytest

from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.recorder import (
    ChannelScanCancelled,
    _response_complete,
    scan_intelbras_channels,
)


def test_rtsp_response_content_length_completes_without_timeout():
    head = b"RTSP/1.0 200 OK\r\nCSeq: 1\r\nContent-Length: 4\r\n\r\n"
    assert not _response_complete(head + b"ab")
    assert _response_complete(head + b"abcd")


def test_rtsp_header_only_error_is_complete():
    assert _response_complete(b"RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\n\r\n")


def test_cancelled_scan_stops_before_network_access():
    event = Event()
    event.set()
    with pytest.raises(ChannelScanCancelled):
        scan_intelbras_channels("192.0.2.1", "admin", "x", cancel_event=event)


def test_old_intelbras_37777_camera_is_promoted_to_recorder(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]["id"]
    device = Device(
        site_id=site,
        name="Intelbras",
        ip="192.168.15.254",
        manufacturer="intelbras",
        model="Intelbras",
        kind=DeviceKind.CAMERA,
        provider="intelbras",
        metadata={"open_ports": [80, 554, 37777], "evidence": ["assinatura HTTP compatível com intelbras"]},
    )
    did = db.upsert_device(device)
    assert db.get_device(did)["kind"] == "camera"
    assert db.normalize_known_device_classification() == 1
    assert db.get_device(did)["kind"] == "xvr"
