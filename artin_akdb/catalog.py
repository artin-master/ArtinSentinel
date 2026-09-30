from __future__ import annotations

from .models import KnowledgeRecord


def _id(key: str) -> str:
    return f"artin.device.{key}"


CORE_RECORDS: tuple[KnowledgeRecord, ...] = (
    KnowledgeRecord(
        stable_id=_id("intelbras-vipc-1230-d-g2"), manufacturer="Intelbras",
        family="VIPC", model="VIPC 1230 D G2", canonical_type="camera-fixed", subtype="fixed/bullet",
        aliases=("VIPC-1230-D-G2", "VIPC1230DG2"),
        capabilities=("network-video", "fixed-camera", "dual-stream", "motion-detection", "ir", "poe"),
        protocols=("rtsp", "onvif"), preferred_strategies=("onvif", "rtsp"), avoid_strategies=("recorder-enumeration",), validation_status="documented",
        provenance=("manufacturer-documentation", "onvif-declaration"), domains=("sentinel", "netlens"), revision=2,
        legacy_keys=("intelbras-vipc-1230-d-g2",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-mhdx"), manufacturer="Intelbras",
        family="MHDX", model="MHDX 1004", canonical_type="xvr", subtype="hybrid-recorder",
        aliases=("MHDX1004",), capabilities=("network-video", "hybrid-recorder", "multi-channel", "ip-extra-channel", "four-analog-plus-one-ip"),
        protocols=("rtsp", "onvif-candidate"), preferred_strategies=("intelbras-recorder", "rtsp", "onvif"), validation_status="field-validated",
        provenance=("field-test", "intelbras-support-field-documentation"), domains=("sentinel", "netlens"), revision=4, legacy_keys=("intelbras-mhdx",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-nvd-1416"), manufacturer="Intelbras", family="NVD",
        model="NVD 1416", canonical_type="nvr", aliases=("NVD1416",),
        capabilities=("network-video", "multi-channel"), protocols=("onvif-candidate", "rtsp-candidate"),
        preferred_strategies=("intelbras-recorder", "rtsp-candidate"), validation_status="field-detected",
        provenance=("device-information-screen",), domains=("sentinel", "netlens"),
        revision=1, legacy_keys=("intelbras-nvd-1416",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-nvd-1516"), manufacturer="Intelbras", family="NVD",
        model="NVD 1516", canonical_type="nvr", aliases=("NVD1516",),
        capabilities=("network-video", "multi-channel"), protocols=("onvif-candidate", "rtsp-candidate"),
        preferred_strategies=("intelbras-recorder", "rtsp-candidate"), validation_status="field-detected",
        provenance=("device-information-screen",), domains=("sentinel", "netlens"),
        revision=1, legacy_keys=("intelbras-nvd-1516",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-mhdx-1216"), manufacturer="Intelbras", family="MHDX",
        model="MHDX 1216", canonical_type="xvr", aliases=("MHDX1216",),
        capabilities=("network-video", "multi-channel", "hybrid-recorder"),
        protocols=("onvif-candidate", "rtsp-candidate"),
        preferred_strategies=("intelbras-recorder", "rtsp-candidate"), validation_status="field-detected",
        provenance=("device-information-screen",), domains=("sentinel", "netlens"),
        revision=1, legacy_keys=("intelbras-mhdx-1216",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-imx-c"), manufacturer="Intelbras",
        family="Mibo", model="iMX C", canonical_type="camera-consumer", subtype="consumer/fixed",
        aliases=("iMX C", "iMX-C", "Mibo iMX C"), identifiers=("model:imx-c",),
        capabilities=("network-video", "consumer-camera", "listen-audio-field-validated", "bidirectional-audio-hardware", "aac-audio"),
        protocols=("rtsp", "onvif", "intelbras-1-candidate"), preferred_strategies=("rtsp", "onvif", "intelbras-1-candidate"),
        avoid_strategies=("recorder-enumeration",),
        negative_knowledge=("talkback-local-transport-not-homologated", "onvif-backchannel-not-assumed"),
        validation_status="field-validated",
        provenance=("manufacturer-documentation", "field-test", "field-test-video-audio-listen-0.2.32"),
        domains=("sentinel", "netlens"), revision=1, legacy_keys=("intelbras-imx-c",),
    ),
    KnowledgeRecord(
        stable_id=_id("intelbras-mibo"), manufacturer="Intelbras",
        family="Mibo", model="MiboCam family", canonical_type="camera-consumer", subtype="consumer/fixed",
        aliases=("Mibo", "MiboCam"), capabilities=("network-video", "consumer-camera", "listen-audio-field-validated", "bidirectional-audio-candidate"),
        protocols=("rtsp", "onvif"), preferred_strategies=("onvif", "rtsp"), avoid_strategies=("recorder-enumeration",),
        negative_knowledge=("talkback-local-transport-not-homologated",), validation_status="field-detected",
        provenance=("field-test", "field-test-video-audio-listen-0.2.32"), domains=("sentinel", "netlens"), revision=3, legacy_keys=("intelbras-mibo",),
    ),
    KnowledgeRecord(
        stable_id=_id("hikvision-ds-7216hghi-f1"), manufacturer="Hikvision",
        family="Turbo HD", model="DS-7216HGHI-F1", canonical_type="dvr", subtype="turbo-hd-recorder",
        aliases=("DS 7216HGHI F1", "7216HGHI"), capabilities=("network-video", "hybrid-recorder", "multi-channel", "dual-stream", "recorder-mediated-ptz", "16-analog-inputs", "ip-channel-proxy"),
        protocols=("rtsp", "hikvision-isapi", "hikvision-service-8000", "onvif-candidate"),
        preferred_strategies=("hikvision-isapi", "hikvision-recorder-rtsp", "onvif"), avoid_strategies=("generic-camera-scan",),
        negative_knowledge=("deviceType=IPC-unreliable-for-classification",),
        validation_status="field-validated", provenance=("manufacturer-documentation", "field-test"),
        domains=("sentinel", "netlens"), revision=3, legacy_keys=("hikvision-ds-7216hghi-f1",),
    ),
    KnowledgeRecord(
        stable_id=_id("hikvision-generic"), manufacturer="Hikvision",
        family="Hikvision", canonical_type="unknown", capabilities=("network-device",),
        protocols=("rtsp", "onvif-candidate", "hikvision-isapi", "hikvision-service-8000"),
        validation_status="tested", provenance=("protocol-signature",), domains=("sentinel", "netlens"), revision=2,
        legacy_keys=("hikvision-generic",),
    ),
    KnowledgeRecord(
        stable_id=_id("jfl-hikvision-compatible"), manufacturer="JFL",
        canonical_type="unknown", capabilities=("network-video-candidate",),
        protocols=("hikvision-rtsp-candidate", "onvif-candidate"), validation_status="detected",
        provenance=("compatibility-observation",), domains=("sentinel", "netlens"), revision=2,
        legacy_keys=("jfl-hikvision-compatible",),
    ),
    KnowledgeRecord(
        stable_id=_id("aitek-sigma-seg6050bp"), manufacturer="Aitek",
        family="SIGMA", model="SIGMA-SEG6050BP", variant="H2-52PGX", canonical_type="camera-fixed", subtype="fixed",
        aliases=("SIGMA SEG6050BP",), capabilities=("network-video", "fixed-camera", "dual-stream", "listen-audio"),
        protocols=("rtsp", "onvif"), preferred_strategies=("onvif", "rtsp"), avoid_strategies=("recorder-enumeration",), validation_status="field-validated",
        provenance=("field-test",), domains=("sentinel", "netlens"), revision=2, legacy_keys=("aitek-sigma-seg6050bp",),
    ),
    KnowledgeRecord(
        stable_id=_id("oem-h2-52pgx"), manufacturer="OEM/XM",
        family="H2 platform", model="H2-52PGX", canonical_type="camera-fixed", subtype="fixed/bullet",
        aliases=("H2 52PGX",), identifiers=("model:h2-52pgx",),
        capabilities=("network-video", "fixed-camera", "audio-candidate", "intercom-candidate"),
        protocols=("rtsp-candidate", "onvif-candidate", "http"),
        preferred_strategies=("onvif", "rtsp", "http-fingerprint"), avoid_strategies=("recorder-enumeration", "ptz-scan"),
        validation_status="field-identified", provenance=("field-observation",),
        domains=("sentinel", "netlens"), revision=2, legacy_keys=("oem-h2-52pgx",),
    ),
    KnowledgeRecord(
        stable_id=_id("aitek-camera"), manufacturer="Aitek", canonical_type="camera-fixed", subtype="fixed",
        capabilities=("network-video", "fixed-camera"), protocols=("rtsp-candidate", "onvif-candidate"),
        validation_status="field-validated", provenance=("field-test",), domains=("sentinel", "netlens"), revision=2,
        legacy_keys=("aitek-camera",),
    ),
    KnowledgeRecord(
        stable_id=_id("it-blue-x3-we2q"), manufacturer="IT-Blue",
        family="Speed Dome", model="X3-WE2Q", variant="XM535D1 / V5.02.R02.000A06CD", canonical_type="camera-ptz", subtype="multi-lens/speed-dome",
        aliases=("XM535D1", "000A06CD"), capabilities=("network-video", "ptz", "multi-lens", "multi-view", "fixed-lenses-field-detected", "bidirectional-audio-experimental", "motion-tracking", "human-detection", "ptz-dvrip"),
        protocols=("rtsp", "onvif-candidate", "xm-dvrip-34567", "xm-dvrip-opmonitor-multilens-experimental", "xm-dvrip-talkback-g711a-experimental"), preferred_strategies=("xm-dvrip-34567", "rtsp", "onvif"), avoid_strategies=("recorder-enumeration",), negative_knowledge=("onvif-ptz-unusable-in-field", "zoom-not-confirmed", "xm-dvrip-fixed-lenses-not-homologated", "xm-dvrip-talkback-not-field-validated"), validation_status="field-validated",
        provenance=("field-test", "field-test-0.2.23-candidate", "implementation-0.2.28-experimental", "implementation-0.2.29-experimental", "implementation-0.2.30-capability-scope", "field-test-0.2.32-multilens", "implementation-0.2.33-per-lens-capabilities"), domains=("sentinel", "netlens"), revision=9, legacy_keys=("it-blue-x3-we2q",),
    ),
    KnowledgeRecord(
        stable_id=_id("it-blue-gk7202v300-cloud"), manufacturer="IT-Blue",
        family="Speed Dome", model="GK7202V300", variant="IPC_GK7202V300_LPG-G5-WQ", canonical_type="camera-ptz",
        aliases=("000779SU",), capabilities=("network-video", "ptz-candidate", "pir", "motion-detection", "human-detection", "alarm"),
        protocols=("cloud-observed",), validation_status="field-identified-cloud-only",
        provenance=("field-test",), domains=("sentinel", "netlens"), revision=2, legacy_keys=("it-blue-gk7202v300-cloud",),
    ),
    KnowledgeRecord(
        stable_id=_id("it-blue-camera"), manufacturer="IT-Blue", canonical_type="camera",
        capabilities=("network-video", "bidirectional-audio-candidate"),
        protocols=("rtsp-candidate", "onvif-candidate", "xm-dvrip-34567-candidate"),
        validation_status="field-detected", provenance=("field-test",), domains=("sentinel", "netlens"), revision=2,
        legacy_keys=("it-blue-camera",),
    ),
)

_BY_ID = {r.stable_id: r for r in CORE_RECORDS}
_BY_LEGACY = {key: r for r in CORE_RECORDS for key in r.legacy_keys}


def record_by_id(stable_id: str) -> KnowledgeRecord | None:
    return _BY_ID.get(str(stable_id or ""))


def record_by_legacy_key(key: str) -> KnowledgeRecord | None:
    return _BY_LEGACY.get(str(key or ""))


def public_catalog() -> list[dict]:
    return [record.to_dict() for record in CORE_RECORDS]
