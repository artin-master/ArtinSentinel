from __future__ import annotations

import sys
import os
import json
import shutil
import faulthandler
from datetime import datetime, timedelta
import threading
import time
from math import ceil, sqrt
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from importlib.resources import files
from urllib.parse import urlparse
from .web_services import (
    build_web_service_url, is_transient_web_endpoint,
    web_services_from_checks, ordered_web_services, web_service_candidates,
)

from PySide6.QtCore import Qt, QPoint, QTimer, QRunnable, QThreadPool, QObject, Signal, Slot, QUrl, QSize, QSettings, QDateTime
from PySide6.QtGui import QFont, QIcon, QPixmap, QImage, QAction, QCursor, QDesktopServices, QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QDateTimeEdit,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QFrame,
    QComboBox,
    QSizePolicy,
    QButtonGroup,
    QCheckBox,
    QMenu,
    QToolButton,
    QAbstractItemView,
    QFileDialog,
    QSlider,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QStyle,
    QToolTip,
    QScrollArea,
    QScrollBar,
    QLayout,
)

from . import __version__
from .db import Database, changed_channel_routes
from .paths import data_dir
from .services import discover_network_devices, diagnose, diagnose_endpoints, persist_discovered_web_checks
from .recorder import scan_intelbras_channels, scan_hikvision_channels, diagnose_hikvision_routes, hikvision_compatibility_report, channels_for_live_view
from .ip_camera import scan_direct_camera_streams, DirectCameraScanResult
from .live import DvripLiveStreamSession
from .direct_revalidation import previously_confirmed, diagnostic_line, recoverable_native_channel
from .credential_store import CredentialStore
from .app_auth import AppAuth
from .access_control import AccessControl,requires_permission,authorize
from .media_process import wait_media_sessions, media_session_chain
from .camera_event_ui import CameraEventUi, history_message
from .live import (
    LiveStreamSession, LiveAudioSession, create_live_stream_session, create_live_audio_session,
    local_media_status, ordered_audio_urls, live_session_can_pause_reconnect,
)
from .log_viewer import sanitize_log_text, read_log_tail, filter_log_lines
from .stream_diagnostics import diagnose_saved_streams, STATE_LABELS as STREAM_STATE_LABELS
from .private_update_auth import store_token
from .recording_search import search_recordings, search_recordings_multi, playback_rtsp_url
from .hik_sdk import settings as hik_sdk_settings
from .hik_recording import search_hikvision_recordings, search_hikvision_recordings_multi, hikvision_playback_url, uses_hikvision_recordings
from .recording_export import export_mp4
from .quick_capture import ManualRecording
from .talkback import (
    XmDvripTalkbackSession, IntelbrasHttpTalkbackSession, IntelbrasNetSDKTalkbackSession, MicrophoneInput, AudioInputPreferences,
    discover_microphone_inputs, ffmpeg_microphone_inputs, probe_microphone_level,
    load_audio_input_preferences, save_audio_input_preferences,
    microphone_gain_db_for_percent, microphone_gain_percent_for_db,
    IMPLEMENTED_TALKBACK_PROTOCOLS, TALKBACK_REASONS, talkback_transport,
    talkback_capability_status, talkback_start_readiness, sanitize_talkback_diagnostic,
)
from .intelbras_netsdk import (
    runtime_info as intelbras_netsdk_runtime_info, install_from_official_archive,
    vendor_install_directory, reference_audio_path,
)
from .domain import Device, DeviceKind
from .remote_access import ACCESS_LOCAL, ACCESS_PRIVATE, ACCESS_CONNECTOR, validate_recorder_host, validate_endpoint_url, access_label, preserve_remote_inventory, forwarded_ports
from .intelbras_cloud import is_cloud_device, IntelbrasCloudLiveSession
from .akdb import (
    public_summary, audio_capability, ptz_capability, capability_map, recorder_scan_limit,
    recorder_scan_capacity_for_device,
    canonical_type_label, routing_kind_for_profile, best_profile, reconcile_operational_profile_key,
)
from .device_intelligence import resolve_operational_identity, routing_explanation, recorder_provider_hint, device_visual_name
from .compat_capture import (
    build_compatibility_report, default_filename, write_report,
    build_discovery_homologation_report, discovery_report_filename,
)
from .akdb_shared import sync_shared_akdb, record_compatibility_candidate, record_field_homologation_report
from .akdb_sync import (
    AkdbSyncSettings, load_settings as load_akdb_sync_settings, save_settings as save_akdb_sync_settings,
    get_submission_token, set_submission_token, check_official_update, apply_official_update, submit_pending,
    pending_proposals, export_proposals,
)
from .workspace import SUPPORTED_GRID_COUNTS, smallest_grid_for, next_empty_slot
from .release_notes import RELEASE_TITLE, RELEASE_NOTES, CHANGELOG_TEXT
from .ptz import pulse_move_provider, start_move_provider, stop_device_provider
from .channel_health import probe_recorder_channel_health, channel_health_label
from .performance import process_sample, cpu_percent
from .mic_trace import MicTrace
from .config_portability import export_configuration, import_configuration, FORMAT as PORTABLE_FORMAT
from .intelbras_http import probe_intelbras_http_api, IntelbrasHttpApiReport, post_audio_transport_info
from .updater import (
    UpdateManifest, UpdateSettings, StagedUpdate,
    load_update_settings, save_update_settings, fetch_update_manifest,
    is_newer, mark_checked, should_check_on_startup, stage_update,
    launch_staged_update, resolve_manifest_url,
    other_sentinel_pids,
)


QSS = """
QWidget {
    background:#0b1420;
    color:#dce7f0;
    font-size:13px;
}
QLabel { background:transparent; }
QMainWindow { background:#0b1420; }
QFrame#TopBar {
    background:#142333;
    border-bottom:1px solid #294258;
}
QFrame#BottomBar {
    background:#142333;
    border-top:1px solid #294258;
}
QFrame#SourcePane, QFrame#InspectorPane {
    background:#142333;
    border:1px solid #294258;
    border-radius:8px;
}
QFrame#VideoTile {
    background:#070d15;
    border:1px solid #294258;
    border-radius:7px;
}
QFrame#VideoTile[selected="true"] {
    border:2px solid #37c8e8;
}
QFrame#VideoTile[dragging="true"] {
    border:2px dashed #37c8e8;
}
QLabel#TileHeader {
    background:#142333;
    color:#d8e9ed;
    padding:6px 8px;
    border-top-left-radius:6px;
    border-top-right-radius:6px;
}
QLabel#TileBody {
    background:#03070d;
    color:#8fa6ba;
    font-size:14px;
}
QLabel#TileFooter {
    background:#0d1823;
    color:#94b1b7;
    padding:5px 8px;
    border-bottom-left-radius:6px;
    border-bottom-right-radius:6px;
}
QPushButton {
    background:#182f42;
    border:1px solid #294258;
    border-radius:6px;
    padding:8px 12px;
}
QPushButton:hover { background:#204359; border-color:#37c8e8; }
QPushButton:pressed { background:#1a3548; }
QPushButton#CompactAction {
    padding:7px 10px;
    min-width:0;
}
QPushButton:checked {
    background:#173a4b;
    border-color:#37c8e8;
    color:white;
}
QPushButton:disabled {
    background:#222f38;
    color:#7b8d9d;
    border-color:#34434a;
}
QToolButton#ActionMenu {
    background:#182f42;
    border:1px solid #294258;
    border-radius:6px;
    padding:8px 12px;
}
QToolButton#ActionMenu:hover { background:#204359; }
QToolButton#ActionMenu:pressed { background:#1a3548; }
QToolButton#ToolbarIconAction {
    background:#14232f;
    border:1px solid #294258;
    border-radius:7px;
    padding:5px;
    min-width:30px;
    min-height:28px;
}
QToolButton#ToolbarIconAction:hover { background:#182f42; border-color:#37c8e8; }
QToolButton#ToolbarIconAction:pressed { background:#204359; }
QToolButton#ToolbarIconAction:checked { background:#204359; border-color:#37c8e8; }
QFrame#LiveToolbarGroup {
    background:#14232f;
    border:1px solid #345365;
    border-radius:9px;
}
QLabel#LiveToolbarCaption { color:#8fa6ba; font-size:10px; font-weight:700; }
QComboBox#LiveGridSelector { min-width:96px; padding:6px 8px; }
QToolButton#PlaybackSkipAction {
    background:#172a37;
    border:1px solid #3a596a;
    border-radius:7px;
    padding:6px 9px;
    color:#e2edf3;
    min-height:28px;
}
QToolButton#PlaybackSkipAction:hover { background:#244353; border-color:#608399; }
QToolButton#PlaybackSkipAction:pressed { background:#2b4b5b; }
QToolButton#PlaybackPlayAction, QToolButton#PlaybackStopAction {
    border-radius:7px; padding:6px; min-width:32px; min-height:28px;
}
QToolButton#PlaybackPlayAction, QToolButton#PlaybackStopAction {
    background:#172a37; border:1px solid #3a596a;
}
QToolButton#PlaybackPlayAction:hover, QToolButton#PlaybackStopAction:hover {
    background:#244353; border-color:#608399;
}
QToolButton#PlaybackPlayAction:disabled, QToolButton#PlaybackStopAction:disabled,
QToolButton#PlaybackSkipAction:disabled { background:#222f38; border-color:#34434a; }
QPushButton#PlaybackMarkIn, QPushButton#PlaybackMarkOut, QPushButton#PlaybackExport {
    background:#172a37; border:1px solid #3a596a; color:#e2edf3;
}
QPushButton#PlaybackMarkIn:hover, QPushButton#PlaybackMarkOut:hover,
QPushButton#PlaybackExport:hover { background:#244353; border-color:#608399; }
QPushButton#PlaybackMarkIn:disabled, QPushButton#PlaybackMarkOut:disabled,
QPushButton#PlaybackExport:disabled { background:#222f38; border-color:#34434a; color:#7b8d9d; }
QScrollArea#InspectorScroll {
    background:transparent;
    border:0;
}
QScrollArea#InspectorScroll > QWidget > QWidget { background:transparent; }
QScrollBar:vertical {
    background:#142333;
    width:10px;
    margin:2px 1px 2px 1px;
    border:0;
    border-radius:5px;
}
QScrollBar::handle:vertical {
    background:#3a6570;
    min-height:28px;
    border-radius:4px;
}
QScrollBar::handle:vertical:hover { background:#50849a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QFrame#InspectorSection {
    background:#142333;
    border:1px solid #294258;
    border-radius:7px;
}
QLabel#InspectorSectionTitle {
    color:#a6bec4;
    font-size:10px;
    font-weight:700;
}
QFrame#SelectionCard {
    background:#142333;
    border:1px solid #294758;
    border-radius:9px;
}
QLabel#SelectionTitle {
    color:#e5f2ec;
    font-size:12px;
    font-weight:700;
}
QLabel#SelectionMeta {
    color:#8fa6ba;
    font-size:9px;
}
QLabel#SelectionState {
    color:#63d69d;
    background:#18352e;
    border:1px solid #3d7459;
    border-radius:7px;
    padding:2px 5px;
    font-size:8px;
    font-weight:700;
}
QLabel#SectionGlyph {
    color:#37c8e8;
    min-width:16px;
    max-width:16px;
}
QFrame#PtzPanel {
    background:#0d1925;
    border:1px solid #244a3a;
    border-radius:14px;
}
QLabel#PtzCapabilityBadge {
    color:#7fe3af;
    background:#10271d;
    border:1px solid #2b5c46;
    border-radius:7px;
    padding:2px 6px;
    font-size:8px;
    font-weight:800;
}
QLabel#PtzControlCaption {
    color:#8fa6ba;
    font-size:8px;
    font-weight:700;
}
QLabel#PtzSpeedValue {
    color:#d8efe4;
    background:#12241c;
    border:1px solid #294c3d;
    border-radius:7px;
    padding:2px 6px;
    font-size:9px;
    font-weight:800;
}
QToolButton#PtzPadButton {
    background:#183b3e;
    border:1px solid #457b6c;
    border-radius:13px;
    color:#e8fff4;
    font-size:24px;
    font-weight:700;
    min-width:52px;
    min-height:46px;
}
QToolButton#PtzPadButton:hover { background:#255547; border-color:#62bd8f; }
QToolButton#PtzPadButton:pressed { background:#336d54; border-color:#86dcb0; padding-top:2px; }
QToolButton#PtzStopButton {
    background:#54251f;
    border:1px solid #a45a4e;
    border-radius:18px;
    color:#ffe5df;
    font-size:10px;
    font-weight:900;
    min-width:52px;
    min-height:46px;
}
QToolButton#PtzStopButton:hover { background:#6c3028; border-color:#d07968; }
QToolButton#PtzStopButton:pressed { background:#843a30; padding-top:2px; }
QToolButton#PtzZoomButton {
    background:#142b36;
    border:1px solid #416e69;
    border-radius:10px;
    color:#dff7eb;
    padding:6px 10px;
    font-size:18px;
    font-weight:800;
    min-height:34px;
}
QToolButton#PtzZoomButton:hover { background:#254f46; border-color:#56a67d; }
QToolButton#PtzPadButton:disabled, QToolButton#PtzStopButton:disabled, QToolButton#PtzZoomButton:disabled {
    background:#182630; color:#44534c; border-color:#34434a;
}
QPushButton#TopNav {
    background:transparent;
    border:0;
    border-radius:0;
    padding:17px 14px 14px 14px;
    color:#dce7f0;
    font-weight:600;
}
QPushButton#TopNav:hover { color:white; background:#1a2d3a; }
QPushButton#TopNav:checked {
    color:#37c8e8;
    background:#1a2d3a;
    border-bottom:2px solid #37c8e8;
}
QTableWidget {
    background:#142333;
    alternate-background-color:#142331;
    gridline-color:#294258;
    border:1px solid #294258;
    selection-background-color:#1b465a;
}
QHeaderView::section {
    background:#192d3a;
    padding:8px;
    border:0;
    border-right:1px solid #294258;
    border-bottom:1px solid #294258;
}
QLineEdit, QPlainTextEdit, QComboBox {
    background:#0b1420;
    border:1px solid #294258;
    border-radius:6px;
    padding:7px;
}

QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color:#37c8e8; }
QComboBox::drop-down { border:0; width:24px; }

/* Menus e listas: hover, seleção persistente e itens desabilitados distintos. */
QMenu {
    background:#142333;
    color:#dce7f0;
    border:1px solid #294258;
    border-radius:7px;
    padding:5px;
}

QMenu::item {
    background:transparent;
    color:#dcebed;
    padding:7px 30px 7px 10px;
    margin:1px 2px;
    border-radius:5px;
}

QMenu::item:selected {
    background:#1b465a;
    color:#ffffff;
}

QMenu::item:checked {
    background:#153849;
    color:#37c8e8;
    font-weight:700;
}

QMenu::item:checked:selected {
    background:#22586d;
    color:#ffffff;
}

QMenu::item:disabled {
    background:transparent;
    color:#7b8d9d;
}

QMenu::separator {
    height:1px;
    background:#294258;
    margin:5px 8px;
}

QMenu::right-arrow {
    width:8px;
    height:8px;
}

QComboBox QAbstractItemView {
    background:#142333;
    color:#dcebed;
    border:1px solid #294258;
    outline:0;
    selection-background-color:#1b465a;
    selection-color:#ffffff;
}

QComboBox QAbstractItemView::item {
    min-height:28px;
    padding:4px 8px;
}

QComboBox QAbstractItemView::item:hover {
    background:#1b465a;
    color:#ffffff;
}

QComboBox QAbstractItemView::item:selected {
    background:#22586d;
    color:#ffffff;
}

QComboBox QAbstractItemView::item:disabled {
    color:#7b8d9d;
}
QGroupBox {
    border:1px solid #294258;
    border-radius:8px;
    margin-top:10px;
    padding:10px;
    font-weight:600;
}
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }
QProgressBar {
    border:1px solid #294258;
    border-radius:5px;
    background:#0b1420;
    text-align:center;
}
QProgressBar::chunk { background:#37c8e8; border-radius:4px; }
QTabWidget::pane { border:1px solid #294258; border-radius:6px; top:-1px; }
QTabBar::tab {
    background:#142331;
    color:#dce7f0;
    padding:10px 16px;
    border:1px solid #294258;
    border-bottom:0;
}
QTabBar::tab:selected { background:#153849; color:#37c8e8; }
QTreeWidget {
    background:#0d1925;
    border:0;
    padding:4px;
    selection-background-color:#1b465a;
}
QTreeWidget::item { padding:5px 2px; }
QSplitter::handle { background:#243b4a; width:2px; }
QDateTimeEdit { background:#0b1420; border:1px solid #294258; border-radius:4px; }
QDateTimeEdit:focus { border-color:#37c8e8; }
QSlider::groove:horizontal { height:4px; background:#294258; border-radius:2px; }
QSlider::sub-page:horizontal { background:#37c8e8; border-radius:2px; }
QSlider::handle:horizontal { background:#37c8e8; border:0; width:12px; margin:-4px 0; border-radius:6px; }
QSlider::handle:horizontal:disabled { background:#7b8d9d; }

"""


def resource_path(name: str) -> str:
    return str(files("artin_sentinel.resources").joinpath(name))


def friendly_kind(kind: str) -> str:
    return {
        "camera": "Câmera IP",
        "dvr": "DVR",
        "nvr": "NVR",
        "xvr": "DVR / Multi HD",
        "unknown": "Não identificado",
    }.get((kind or "").lower(), kind or "Não identificado")


def clean_model(manufacturer: str, model: str) -> str:
    manufacturer = (manufacturer or "").strip()
    model = (model or "").strip()
    if not model or (manufacturer and model.casefold() == manufacturer.casefold()):
        return "—"
    return model


def status_dot_icon(state: str, size: int = 10) -> QIcon:
    """Small status marker used by the VMS source tree.

    Color is supplemental: text/tooltips still expose Online/Offline/Unknown so
    the state does not depend on color perception alone.
    """
    colors = {
        "online": "#38d996",
        "offline": "#65736d",
        "attention": "#e8b45e",
        "unknown": "#82938c",
        "channel": "#38d996",
    }
    pix = QPixmap(size + 4, size + 4)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(colors.get((state or "unknown").lower(), colors["unknown"])))
    painter.drawEllipse(2, 2, size, size)
    painter.end()
    return QIcon(pix)


def status_label(state: str) -> str:
    return {"online": "Online", "offline": "Offline", "unknown": "Estado desconhecido"}.get(
        (state or "unknown").lower(), state or "Estado desconhecido"
    )


def channel_matches_capability_scope(channel, scope: str) -> bool:
    """Resolve model capabilities at channel/lens granularity.

    Multi-lens cameras must not project PTZ/talkback from the primary moving
    lens onto fixed auxiliary views. ``primary`` accepts the first logical
    channel or an explicit PTZ/principal source label; ``all`` remains the
    backwards-compatible default for single-lens devices.
    """
    scope = str(scope or "all").casefold()
    if scope in {"", "all"}:
        return True
    if scope in {"none", "disabled"}:
        return False
    try:
        channel_no = int(channel["channel_no"] or 0)
    except Exception:
        try:
            channel_no = int(getattr(channel, "channel_no", 0) or 0)
        except Exception:
            channel_no = 0
    try:
        source_name = str(channel["source_name"] or channel["name"] or "").casefold()
    except Exception:
        source_name = str(getattr(channel, "source_name", "") or getattr(channel, "name", "") or "").casefold()
    if scope == "primary":
        return "lente fixa" not in source_name and (
            channel_no in {0, 1} or "ptz" in source_name or "principal" in source_name
        )
    return False


def channel_audio_info(device, channel) -> dict:
    """Merge field-probed channel audio with conservative AKDB knowledge."""
    if is_cloud_device(device):
        return dict(mode="none", observed_mode="none", known_mode="unknown", profile_key="",
                    codec="", rate=0, detail="Áudio não validado pela ponte piloto.",
                    can_listen=False, can_probe_listen=True, can_talk=False, talkback_pending=False,
                    label="Escuta Cloud • verificar faixa", talkback_protocol="", talkback_state="unsupported",
                    talkback_reason="Áudio não validado pela ponte piloto.", talkback_transport_label="",
                    talkback_scope="", talkback_validation="", talkback_base_url="",
                    talkback_audio_channel=0, talkback_netsdk_ports=[], talkback_netsdk_runtime="",
                    http_output_device_level=False)
    def value(row, key, default=""):
        try:
            return row[key]
        except Exception:
            return default
    mode = str(value(channel, "audio_mode", "unknown") or "unknown")
    codec = str(value(channel, "audio_codec", "") or "")
    rate = int(value(channel, "audio_sample_rate", 0) or 0)
    detail = str(value(channel, "audio_detail", "") or "")
    profile_key = ""
    metadata = {}
    try:
        metadata = json.loads(value(device, "metadata_json", "{}") or "{}")
        if isinstance(metadata, dict):
            profile_key = str(metadata.get("akdb_profile") or "")
        else:
            metadata = {}
    except Exception:
        metadata = {}
    # Older field inventories may predate persistent akdb_profile metadata.
    # Recover only from conservative model/manufacturer evidence; required-token
    # profiles (such as IT-Blue X3-WE2Q) cannot match on manufacturer alone.
    if not profile_key:
        identity_text = " ".join(
            str(value(device, key, "") or "")
            for key in ("name", "model", "detected_name", "detected_model")
        )
        manufacturer = str(value(device, "detected_manufacturer", "") or value(device, "manufacturer", "") or "")
        matched = best_profile(text=identity_text, manufacturer=manufacturer)
        if matched:
            _score, profile = matched
            profile_key = profile.key
    provider_name = str(value(device, "provider", "") or "")
    # Reconcile stale generic field identities before resolving audio. This is
    # deliberately narrower than manufacturer-wide inheritance and mirrors the
    # already field-working PTZ identity fallback.
    identity_text = " ".join(
        str(value(device, key, "") or "")
        for key in ("name", "model", "detected_name", "detected_model", "manufacturer", "detected_manufacturer")
    )
    profile_key = reconcile_operational_profile_key(
        profile_key=profile_key, provider=provider_name, identity_text=identity_text
    )
    # Older X3 inventories can retain a generic Web Viewer/device identity.
    # The primary lens itself carries the field-validated X3 detail already
    # used by PTZ. Apply that same narrow evidence to its MIC capability.
    if ("it-blue" in f"{provider_name} {value(device, 'manufacturer')}".casefold()
            and str(value(channel, "source_name") or "").casefold().strip() == "lente ptz"
            and "it-blue x3" in str(value(channel, "detail") or "").casefold()):
        profile_key = "it-blue-x3-we2q"
    known = audio_capability(provider=provider_name, profile_key=profile_key)
    known_mode = str(known.get("mode") or "unknown")
    observed_mode = mode
    if mode in {"", "unknown"} and known_mode not in {"", "unknown"}:
        mode = known_mode
    can_listen = bool(codec) or mode in {"listen", "bidirectional"}
    # A recorder channel with validated video can still carry audio even when a
    # previous bounded ffprobe did not finish in time.  Let the operator request
    # an on-demand audio probe instead of hiding the speaker button forever.
    route_kind = str(value(channel, "route_kind", "via_recorder") or "via_recorder")
    channel_kind = str(value(channel, "channel_kind", "unknown") or "unknown")
    has_rtsp = bool(value(channel, "main_rtsp_url", "") or value(channel, "sub_rtsp_url", "") or value(channel, "rtsp_url", ""))
    available = bool(value(channel, "available", 0))
    # An IP/proxy channel behind a recorder may expose audio differently from
    # the first bounded ffprobe result. Field validation on MHDX channel 5
    # proved that the vendor client can hear audio even when Sentinel metadata
    # still says none/unknown, so that route remains explicitly re-checkable.
    recheckable_proxy = route_kind == "via_recorder" and channel_kind == "ip"
    # Recorder-backed IP/proxy channels remain probeable even when a previous
    # bounded inventory scan marked availability stale. Field MHDX channel 5 can
    # still open video/audio through the DVR in that state.
    can_probe_listen = bool(
        has_rtsp and route_kind in {"via_recorder", "direct"}
        and ((available and mode != "none") or recheckable_proxy)
    )
    talkback_protocol = str(known.get("talkback_protocol") or "")
    talkback_scope = str(known.get("talkback_scope") or "all")
    talkback_validation = str(known.get("talkback_validation") or "unknown")

    # 0.2.39 field result: postAudio is a real device-level audio output on the
    # MHDX, but it did NOT forward speech to the Mibo behind CAM 5. Conversely,
    # direct iMX C firmware closes both documented HTTP framing modes while the
    # official mobile app talkback works. Therefore direct iMX C now prefers the
    # official NetSDK talk path; recorder-backed channels no longer inherit the
    # MHDX device-level HTTP output as if it were per-channel talkback.
    http_transport = post_audio_transport_info(metadata)
    http_post_audio_ready = bool(http_transport.get("ready"))
    http_base_url = str(http_transport.get("base_url") or "")
    netsdk_info = intelbras_netsdk_runtime_info()
    netsdk_direct_candidate = bool(
        profile_key == "intelbras-imx-c"
        and route_kind == "direct"
    )
    raw_ports = metadata.get("open_ports") if isinstance(metadata, dict) else []
    open_ports = [int(p) for p in (raw_ports or []) if str(p).isdigit()]
    netsdk_ports = [p for p in (37777, 37778, 34567) if p in open_ports]
    for fallback_port in (37777, 37778, 34567):
        if fallback_port not in netsdk_ports:
            netsdk_ports.append(fallback_port)

    if netsdk_direct_candidate:
        # iMX C field validation proved HTTP postAudio is rejected even though
        # the camera advertises an output. Keep the native NetSDK path selected
        # even when its local runtime is not installed, so the UI explains the
        # missing dependency instead of silently retrying the known-bad HTTP path.
        talkback_protocol = "intelbras-netsdk-talk-experimental"
        talkback_validation = "experimental"
        talkback_scope = "primary"
    elif http_post_audio_ready and route_kind == "direct":
        # Keep HTTP available for other direct Intelbras/Dahua-compatible IPCs
        # whose concrete firmware advertises an audio output. iMX C is routed
        # above to NetSDK because HTTP was rejected in field tests.
        talkback_protocol = "intelbras-http-postaudio-experimental"
        talkback_validation = "experimental"
        talkback_scope = "primary"

    scope_ok = channel_matches_capability_scope(channel, talkback_scope)
    operational_talkback_protocols = IMPLEMENTED_TALKBACK_PROTOCOLS
    protocol_ready = bool(
        talkback_protocol in operational_talkback_protocols
        and (talkback_protocol != "intelbras-netsdk-talk-experimental" or netsdk_info.available)
    )
    talkback_pending = bool(
        (known_mode == "bidirectional" or netsdk_direct_candidate or (http_post_audio_ready and route_kind == "direct"))
        and not protocol_ready
    )
    talkback_state = talkback_capability_status(
        talkback_protocol, scope_ok=scope_ok,
        evidence=bool(netsdk_direct_candidate or http_post_audio_ready
                      or mode == "bidirectional" or known_mode == "bidirectional"),
        route_kind=route_kind, netsdk_available=bool(netsdk_info.available),
    )
    can_talk = talkback_state == "ready"
    talkback_pending = talkback_pending or (scope_ok and talkback_state in {"recorder_route", "runtime_missing"})
    transport_info = talkback_transport(talkback_protocol)
    label_parts = []
    if codec:
        label_parts.append(codec.upper() + (f" {rate} Hz" if rate else ""))
    elif can_listen:
        label_parts.append("áudio detectado")
    elif can_probe_listen:
        label_parts.append("áudio a verificar")
    if can_talk:
        label_parts.append("MIC experimental" if talkback_validation == "experimental" else "bidirecional")
    elif talkback_pending and scope_ok:
        label_parts.append("MIC pendente de transporte local")
    return {
        "mode": mode,
        "observed_mode": observed_mode,
        "known_mode": known_mode,
        "profile_key": profile_key,
        "codec": codec,
        "rate": rate,
        "detail": detail,
        "can_listen": can_listen,
        "can_probe_listen": can_probe_listen,
        "can_talk": can_talk,
        "talkback_pending": talkback_pending and scope_ok,
        "label": " • ".join(label_parts),
        "talkback_protocol": talkback_protocol,
        "talkback_state": talkback_state,
        "talkback_reason": TALKBACK_REASONS[talkback_state],
        "talkback_transport_label": transport_info.label if transport_info else "Não implementado",
        "talkback_scope": talkback_scope,
        "talkback_validation": talkback_validation,
        "talkback_base_url": http_base_url if http_post_audio_ready else "",
        "talkback_audio_channel": 1 if http_post_audio_ready else 0,
        "talkback_netsdk_ports": netsdk_ports if netsdk_direct_candidate else [],
        "talkback_netsdk_runtime": netsdk_info.detail if netsdk_direct_candidate else "",
        "http_output_device_level": bool(http_post_audio_ready and route_kind == "via_recorder"),
    }


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)
    diagnostic = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn, *args, with_progress=False, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.with_progress = with_progress
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=self.signals.progress.emit, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.signals.finished.emit()


class RecordingTimeline(QWidget):
    """Recorder time axis: searched period, recorded spans and hover clock."""

    timeChosen = Signal(object)
    timeHovered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(104)
        self.setMouseTracking(True)
        self.start = None
        self.end = None
        self.recordings = ()
        self.channels = ()
        self.cursor_time = None
        self.view_start = self.view_end = None
        self.view_scroll = QScrollBar(Qt.Horizontal, self)
        self.view_scroll.setStyleSheet("""
            QScrollBar:horizontal { background:#142333; border:0; height:12px; margin:0; }
            QScrollBar::handle:horizontal { background:#50849a; min-width:32px; border-radius:4px; }
            QScrollBar::handle:horizontal:hover { background:#37c8e8; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
        """)
        self.view_scroll.setToolTip("Deslocar a faixa de horários ampliada")
        self.view_scroll.valueChanged.connect(self._scroll_view)
        self.zoom_reset = QToolButton(self)
        self.zoom_reset.setText("Período todo")
        self.zoom_reset.setToolTip("Voltar a mostrar todo o período pesquisado")
        self.zoom_reset.clicked.connect(self.reset_view)
        self.setToolTip("Roda do mouse: ampliar/reduzir horários. Use a barra para deslocar a faixa ampliada.")
        self.view_scroll.hide();self.zoom_reset.hide()

    def set_period(self, start, end, recordings=(), channels=()):
        same_period = (self.start,self.end)==(start,end)
        self.start, self.end = start, end
        self.recordings = tuple(recordings)
        self.channels = tuple(channels)
        self.setMinimumHeight(104 + max(0, len(self.channels) - 1) * 24)
        self.cursor_time = None
        if not same_period or self.view_start is None:
            self.view_start,self.view_end=start,end
        self._sync_view_controls()
        self.update()

    def _sync_view_controls(self):
        valid = self.start is not None and self.end is not None and self.end > self.start
        zoomed = valid and (self.view_end-self.view_start).total_seconds() < (self.end-self.start).total_seconds()-.01
        self.view_scroll.setVisible(zoomed);self.zoom_reset.setVisible(zoomed)
        if valid:
            span=(self.view_end-self.view_start).total_seconds()
            self.view_scroll.blockSignals(True)
            self.view_scroll.setRange(0,max(0,round((self.end-self.start).total_seconds()-span)))
            self.view_scroll.setPageStep(max(1,round(span)))
            self.view_scroll.setSingleStep(max(1,min(300,round(span/10))))
            self.view_scroll.setValue(round((self.view_start-self.start).total_seconds()))
            self.view_scroll.blockSignals(False)
        left=self._left()
        self.view_scroll.setGeometry(left,self.height()-20,max(1,self.width()-left-122),18)
        self.zoom_reset.setGeometry(max(left,self.width()-114),self.height()-22,96,22)

    def _set_view(self, offset, span):
        total=(self.end-self.start).total_seconds()
        span=min(total,max(min(900,total),span))
        offset=max(0,min(total-span,offset))
        self.view_start=self.start+timedelta(seconds=offset)
        self.view_end=self.view_start+timedelta(seconds=span)
        self._sync_view_controls();self.update()

    def _scroll_view(self, value):
        if self.view_start is not None and self.view_end is not None:
            self._set_view(value,(self.view_end-self.view_start).total_seconds())

    def reset_view(self):
        if self.start is not None and self.end is not None:
            self._set_view(0,(self.end-self.start).total_seconds())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self,'view_scroll'):self._sync_view_controls()

    def wheelEvent(self, event):
        anchor=self.time_at(event.position().x())
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if anchor is None or not delta:
            event.ignore();return
        ratio=min(1,max(0,(event.position().x()-self._left())/max(1,self.width()-self._left()-18)))
        total=(self.end-self.start).total_seconds()
        span=(self.view_end-self.view_start).total_seconds()
        new_span=min(total,max(min(900,total),span/(2**max(-8,min(8,delta/120)))))
        self._set_view((anchor-self.start).total_seconds()-ratio*new_span,new_span)
        event.accept()

    def _left(self):
        return 70 if self.channels else 18

    def time_at(self, x):
        if not self.start or not self.end or self.end <= self.start:
            return None
        ratio = min(1.0, max(0.0, (x - self._left()) / max(1, self.width() - self._left() - 18)))
        return self.view_start + timedelta(seconds=ratio * (self.view_end - self.view_start).total_seconds())

    def _x(self, point):
        duration = (self.view_end - self.view_start).total_seconds()
        return self._left() + int((self.width() - self._left() - 18) * (point - self.view_start).total_seconds() / duration)

    def five_minute_marks(self):
        if not self.start or not self.end or self.end <= self.start:
            return ()
        point = self.view_start.replace(minute=(self.view_start.minute // 5) * 5, second=0, microsecond=0)
        if point < self.view_start:
            point += timedelta(minutes=5)
        count = min(2048, max(0, int((self.view_end - point).total_seconds() // 300) + 1))
        return tuple(point + timedelta(minutes=5 * i) for i in range(count))

    def ruler_time_at(self, x, y):
        point = self.time_at(x)
        if point is not None and 28 <= y <= 43:
            marks = self.five_minute_marks()
            if marks:
                nearest = min(marks, key=lambda t: abs(self._x(t) - x))
                if abs(self._x(nearest) - x) <= 4:
                    return nearest
        return point

    def mouseMoveEvent(self, event):
        point = self.ruler_time_at(event.position().x(), event.position().y())
        if point:
            self.timeHovered.emit(point)
            QToolTip.showText(event.globalPosition().toPoint(), point.strftime("%d/%m/%Y %H:%M:%S"), self)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = self.ruler_time_at(event.position().x(), event.position().y())
            if point:
                self.cursor_time = point
                self.timeChosen.emit(point)
                self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b1420"))
        if not self.start or not self.end or self.end <= self.start:
            painter.setPen(QColor("#8fa6ba"))
            painter.drawText(18, 45, "Busque gravações para visualizar os horários")
            return
        left, right = self._left(), self.width() - 18
        channels = self.channels or (None,)
        for lane, channel in enumerate(channels):
            y = 43 + lane * 24
            painter.fillRect(left, y, max(1, right - left), 17, QColor("#142333"))
            if channel is not None:
                painter.setPen(QColor("#8fa6ba"))
                painter.drawText(8, y + 13, f"CAM {channel}")
        period = (self.view_end - self.view_start).total_seconds()
        for recording in self.recordings:
            try:
                begin = max(self.view_start, datetime.strptime(recording.start, "%Y-%m-%d %H:%M:%S"))
                finish = min(self.view_end, datetime.strptime(recording.end, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if finish > begin:
                x1, x2 = self._x(begin), self._x(finish)
                lane = channels.index(recording.channel) if recording.channel in channels else 0
                painter.fillRect(x1, 43 + lane * 24, max(2, x2 - x1), 17, QColor("#42b983"))
        painter.setPen(QColor("#dce7f0"))
        last_label = left - 70
        hours_between_labels = max(1, ceil(70 / max(1, (right - left) * 3600 / period)))
        for t in self.five_minute_marks():
            x = self._x(t)
            major = t.minute == 0
            painter.setPen(QColor("#dce7f0" if major else "#8fa6ba" if t.minute % 15 == 0 else "#506779"))
            painter.drawLine(x, 29 if major else 34 if t.minute % 15 == 0 else 38, x, 42)
            label_x = max(left, min(right - 45, x - 22))
            if (period <= 7200 or (major and t.hour % hours_between_labels == 0)) and label_x - last_label >= 50:
                painter.drawText(label_x, 24, t.strftime("%H:%M"))
                last_label = label_x
        if self.cursor_time and self.view_start <= self.cursor_time <= self.view_end:
            x = self._x(self.cursor_time)
            painter.setPen(QColor("#37c8e8"))
            painter.drawLine(x, 33, x, 66 + (len(channels) - 1) * 24)
            painter.setBrush(QColor("#37c8e8"))
            painter.drawPolygon(QPolygon([QPoint(x - 4, 28), QPoint(x + 4, 28), QPoint(x, 34)]))
        painter.setPen(QColor("#8fa6ba"))
        painter.drawText(left, 77 + (len(channels) - 1) * 24,
                         f"Zoom {(self.end-self.start).total_seconds()/period:g}× • roda: ampliar/reduzir • traços: 5 min • destaques: 15 min / 1 h")


class PlaybackSeekSlider(QSlider):
    hoverSeconds = Signal(int)

    def mouseMoveEvent(self, event):
        if self.isEnabled():
            ratio = min(1.0, max(0.0, event.position().x() / max(1, self.width())))
            seconds = int(self.minimum() + ratio * (self.maximum() - self.minimum()))
            self.hoverSeconds.emit(seconds)
        super().mouseMoveEvent(event)


class VideoTile(QFrame):
    activated = Signal(object)
    doubleActivated = Signal(object)
    closeRequested = Signal(object)
    audioRequested = Signal(object)
    talkRequested = Signal(object)
    moveRequested = Signal(object, object)

    def __init__(self, index: int):
        super().__init__()
        self.index = index
        self.source = None
        self._loading_bar = None
        self._dense_count = 1
        self._audio_can_listen = False
        self._audio_can_talk = False
        self._audio_talk_pending = False
        self._audio_talk_reason = ""
        self._display_mode = "fill"
        self._drag_origin = None
        self._dragging = False
        self.setObjectName("VideoTile")
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(220, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_bar = QFrame()
        header_bar.setObjectName("TileHeaderBar")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 2, 0)
        header_layout.setSpacing(0)
        self.header = QLabel(f"Janela {index + 1}")
        self.header.setObjectName("TileHeader")
        self.header.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.camera_event_badge = QLabel("")
        self.camera_event_badge.setStyleSheet("color:#ffc36b;font-size:10px;padding:0 4px")
        self.camera_event_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.camera_event_badge.hide()
        self.stream_badge = QLabel("")
        self.stream_badge.setToolTip("Stream efetivamente em uso")
        self.stream_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.stream_badge.setStyleSheet("color:#55d996;font-size:10px;font-weight:700;padding:0 4px")
        self.stream_badge.hide()
        self.audio_button = QToolButton()
        self.audio_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        self.audio_button.setIconSize(QSize(15, 15))
        self.audio_button.setToolTip("Ouvir áudio deste canal")
        self.audio_button.setAutoRaise(True)
        self.audio_button.setCheckable(True)
        self.audio_button.setFixedSize(28, 24)
        self.audio_button.hide()
        self.audio_button.clicked.connect(lambda: self.audioRequested.emit(self))
        self.talk_button = QToolButton()
        self.talk_button.setText("MIC")
        self.talk_button.setToolTip("Áudio bidirecional detectado; Push-to-Talk aguarda validação do protocolo")
        self.talk_button.setAutoRaise(True)
        self.talk_button.setFixedSize(34, 24)
        self.talk_button.hide()
        self.talk_button.clicked.connect(lambda: self.talkRequested.emit(self))
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip("Fechar somente este canal")
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(26, 24)
        self.close_button.hide()
        self.close_button.clicked.connect(lambda: self.closeRequested.emit(self))
        header_layout.addWidget(self.header, 1)
        self.media_badge=QLabel('');self.media_badge.setStyleSheet('color:#8fcada;font-size:9px;padding:0 3px');self.media_badge.hide()
        header_layout.addWidget(self.media_badge)
        header_layout.addWidget(self.camera_event_badge, 0, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.stream_badge, 0, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.audio_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.talk_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.close_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.body = ZoomImageLabel(index, "Duplo clique em uma câmera/canal\npara abrir nesta janela")
        self.body.setObjectName("TileBody")
        self.body.clicked.connect(lambda: self.activated.emit(self))
        self.body.doubleClicked.connect(lambda _index: self.doubleActivated.emit(self))
        self.body.setAlignment(Qt.AlignCenter)
        self.body.setWordWrap(True)
        self.body.setMinimumSize(1, 1)
        self.footer = QLabel("Sem fonte • somente leitura")
        self.footer.setObjectName("TileFooter")
        self.footer.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(header_bar)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.footer)

    def mousePressEvent(self, event):
        self.activated.emit(self)
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None and (event.buttons() & Qt.LeftButton):
            distance = (event.position().toPoint() - self._drag_origin).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._dragging = True
                self.setProperty("dragging", True)
                self.style().unpolish(self); self.style().polish(self)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self.moveRequested.emit(self, event.globalPosition().toPoint())
        self._drag_origin = None
        if self._dragging:
            self._dragging = False
            self.setProperty("dragging", False)
            self.style().unpolish(self); self.style().polish(self)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleActivated.emit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_camera_event_badge(self, text):
        self.camera_event_badge.setText(text)
        self.camera_event_badge.setVisible(bool(text) and bool(self.source))

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_loading(self, busy):
        if busy and self.source:
            if self._loading_bar is None:
                from .live_loading import CameraLoadingBar
                self._loading_bar = CameraLoadingBar(self.body)
            self._loading_bar.reposition()
            self._loading_bar.show(); self._loading_bar.raise_()
        elif self._loading_bar is not None:
            self._loading_bar.hide()

    def sync_loading(self, session):
        finished = getattr(session, "_finished", None)
        busy = (session is not None and getattr(session, "current_state", "") in {"connecting", "retrying"}
                and not (finished is not None and finished.is_set()))
        self.set_loading(busy)

    def clear_source(self):
        self.set_loading(False)
        self.source = None
        self.set_camera_event_badge("")
        self.body.reset_zoom()
        self.header.setText(f"Janela {self.index + 1}")
        self.media_badge.clear();self.media_badge.hide()
        self.body.clear()
        self.body.setPixmap(QPixmap())
        self.body.setText("Duplo clique em uma câmera/canal\npara abrir nesta janela")
        self.footer.setText("Sem fonte • somente leitura")
        self.close_button.hide()
        self.stream_badge.hide()
        self.audio_button.hide()
        self.audio_button.setChecked(False)
        self.talk_button.hide()
        self.talk_button.setEnabled(False)
        self.talk_button.setText("MIC")
        self.talk_button.setStyleSheet("")
        self._audio_can_listen = False
        self._audio_can_talk = False
        self._audio_talk_pending = False
        self._audio_talk_reason = ""
        self._display_mode = "fill"

    def set_source(self, title: str, subtitle: str, footer: str, payload=None):
        self.set_loading(False)
        self.source = payload
        self.set_camera_event_badge("")
        self.body.reset_zoom()
        self.header.setText(title)
        self.body.clear()
        self.body.setPixmap(QPixmap())
        self.body.setText(subtitle)
        self.footer.setText(footer)
        self.close_button.show()
        if isinstance(payload, dict):
            self.set_display_mode(payload.get("display_mode", "fill"))
            self.set_stream_indicator(payload.get("active_stream", ""), connecting=True)

    def _content_snapshot(self):
        pix = self.body.pixmap()
        pix_copy = QPixmap(pix) if pix is not None and not pix.isNull() else QPixmap()
        return {
            "source": dict(self.source) if isinstance(self.source, dict) else self.source,
            "loading": self._loading_bar is not None and not self._loading_bar.isHidden(),
            "header": self.header.text(),
            "body_text": self.body.text(),
            "pixmap": pix_copy,
            "footer": self.footer.text(),
            "close": self.close_button.isVisible(),
            "listen": self._audio_can_listen,
            "talk": self._audio_can_talk,
            "talk_pending": self._audio_talk_pending,
            "talk_reason": self._audio_talk_reason,
            "audio_active": self.audio_button.isChecked(),
            "audio_tip": self.audio_button.toolTip(),
            "stream_text": self.stream_badge.text(),
            "stream_tip": self.stream_badge.toolTip(),
            "stream_style": self.stream_badge.styleSheet(),
            "stream_visible": self.stream_badge.isVisible(),
            "display_mode": self._display_mode,
        }

    def _apply_content_snapshot(self, state):
        self.set_camera_event_badge("")
        self.source = state.get("source")
        self.body.clear(); self.body.setPixmap(QPixmap())
        if not self.source:
            self.header.setText(f"Janela {self.index + 1}")
            self.body.setText("Duplo clique em uma câmera/canal\npara abrir nesta janela")
            self.footer.setText("Sem fonte • somente leitura")
        else:
            self.header.setText(state.get("header", f"Janela {self.index + 1}"))
            pix = state.get("pixmap")
            if pix is not None and not pix.isNull():
                self.body.setPixmap(pix)
            else:
                self.body.setText(state.get("body_text", ""))
            self.footer.setText(state.get("footer", ""))
        self.close_button.setVisible(bool(state.get("close")) and bool(self.source))
        self._audio_can_listen = bool(state.get("listen"))
        self._audio_can_talk = bool(state.get("talk"))
        self._audio_talk_pending = bool(state.get("talk_pending"))
        self._audio_talk_reason = str(state.get("talk_reason") or "")
        compact_ok = self._dense_count < 25
        self.audio_button.setVisible(bool(self.source) and self._audio_can_listen and compact_ok)
        self._apply_talk_button_state(compact_ok=compact_ok)
        self.audio_button.setChecked(bool(state.get("audio_active")) and self._audio_can_listen)
        self.audio_button.setToolTip(state.get("audio_tip") or "Ouvir áudio deste canal")
        self.stream_badge.setText(state.get("stream_text", ""))
        self.stream_badge.setToolTip(state.get("stream_tip", ""))
        self.stream_badge.setStyleSheet(state.get("stream_style", ""))
        self.stream_badge.setVisible(bool(state.get("stream_visible")) and bool(self.source))
        self.set_display_mode(state.get("display_mode", "fill"))
        self.set_loading(bool(state.get("loading")))

    def swap_content_with(self, other):
        left = self._content_snapshot()
        right = other._content_snapshot()
        self._apply_content_snapshot(right)
        other._apply_content_snapshot(left)

    def update_media_badge(self,session):
        from .media_observation import session_label
        text=session_label(session)
        if self.source and self.source.get('manufacturer'):
            from .brand_tree import registry
            brand=registry().resolve(self.source['manufacturer'])
            if brand:
                self.media_badge.setStyleSheet('color:'+brand.color+';font-size:9px;padding:0 3px')
        if self.media_badge.text()!=text:
            self.media_badge.setText(text);self.media_badge.setToolTip(text)
        self.media_badge.setVisible(self._dense_count<16)

    def set_stream_indicator(self, kind: str = "", *, connecting: bool = False):
        kind = str(kind or "").lower()
        if not self.source or kind not in {"main", "sub"}:
            self.stream_badge.hide()
            return
        dense = self._dense_count >= 64
        label = "M" if kind == "main" else "S"
        full = "MAIN" if kind == "main" else "SUB"
        self.stream_badge.setText(("○ " if connecting else "● ") + (label if dense else full))
        self.stream_badge.setStyleSheet(
            ("color:#d5a94f;" if connecting else "color:#55d996;")
            + "font-size:10px;font-weight:700;padding:0 4px"
        )
        self.stream_badge.setToolTip(f"Stream efetivamente em uso: {full}")
        self.stream_badge.show()

    def _apply_talk_button_state(self, *, compact_ok: bool | None = None):
        if compact_ok is None:
            compact_ok = self._dense_count < 25
        visible = bool(self.source) and bool(compact_ok) and bool(self._audio_can_talk or self._audio_talk_pending)
        self.talk_button.setVisible(visible)
        if not visible:
            return
        if self._audio_can_talk:
            self.talk_button.setText("MIC")
            self.talk_button.setEnabled(True)
            self.talk_button.setStyleSheet("")
            self.talk_button.setToolTip(
                "MIC disponível neste canal; use o painel Áudio para selecionar/testar o microfone e iniciar o Push-to-Talk"
            )
            if self._dense_count < 25:
                self.talk_button.setFixedSize(34, 24)
        else:
            # Keep the unavailable control deliberately visible. Field feedback
            # showed that a merely grey/disabled MIC looks like a rendering bug.
            self.talk_button.setText("MIC OFF")
            self.talk_button.setEnabled(False)
            self.talk_button.setStyleSheet(
                "QToolButton{color:#e4c887;background:#2a2417;border:1px solid #665329;"
                "border-radius:5px;padding:0 5px;font-weight:700;}"
                "QToolButton:disabled{color:#e4c887;background:#2a2417;border:1px solid #665329;}"
            )
            self.talk_button.setToolTip(
                self._audio_talk_reason or "MIC indisponível neste canal • talkback ainda não homologado para este caminho"
            )
            if self._dense_count < 25:
                self.talk_button.setFixedSize(52, 24)

    def set_audio_capabilities(
        self, can_listen: bool, can_talk: bool, *, active: bool = False, label: str = "",
        talk_pending: bool = False, talk_reason: str = "",
    ):
        self._audio_can_listen = bool(can_listen)
        self._audio_can_talk = bool(can_talk)
        self._audio_talk_pending = bool(talk_pending and not can_talk)
        self._audio_talk_reason = str(talk_reason or "")
        compact_ok = self._dense_count < 25
        self.audio_button.setVisible(bool(self.source) and self._audio_can_listen and compact_ok)
        self.audio_button.setChecked(bool(active) and self._audio_can_listen)
        if label:
            self.audio_button.setToolTip(f"Ouvir áudio deste canal • {label}")
        else:
            self.audio_button.setToolTip("Ouvir áudio deste canal")
        self._apply_talk_button_state(compact_ok=compact_ok)

    def set_audio_active(self, active: bool):
        self.audio_button.blockSignals(True)
        self.audio_button.setChecked(bool(active) and self._audio_can_listen)
        self.audio_button.blockSignals(False)

    def set_dense_mode(self, count: int):
        """Adapt tile chrome/minimum size for large monitoring mosaics."""
        count = int(count or 1)
        self._dense_count = count
        if count >= 25:
            self.audio_button.hide()
            self.talk_button.hide()
        elif self.source:
            self.audio_button.setVisible(self._audio_can_listen)
            self._apply_talk_button_state(compact_ok=True)
        if count >= 64:
            self.setMinimumSize(34, 28)
            self.header.setStyleSheet("font-size:8px;padding:1px 3px")
            self.footer.hide()
            self.close_button.setFixedSize(18, 18)
            self.close_button.setStyleSheet("font-size:10px;padding:0")
            self.audio_button.setFixedSize(18, 18)
            self.talk_button.setFixedSize(24, 18)
        elif count >= 25:
            self.setMinimumSize(60, 45)
            self.header.setStyleSheet("font-size:9px;padding:2px 4px")
            self.footer.show()
            self.footer.setStyleSheet("font-size:8px;padding:1px 4px")
            self.close_button.setFixedSize(20, 20)
            self.close_button.setStyleSheet("font-size:11px;padding:0")
            self.audio_button.setFixedSize(20, 20)
            self.talk_button.setFixedSize(28, 20)
        else:
            self.setMinimumSize(120, 80)
            self.header.setStyleSheet("")
            self.footer.show()
            self.footer.setStyleSheet("")
            self.close_button.setFixedSize(26, 24)
            self.close_button.setStyleSheet("")
            self.audio_button.setFixedSize(28, 24)
            self.talk_button.setFixedSize(52 if self._audio_talk_pending and not self._audio_can_talk else 34, 24)

    def set_display_mode(self, mode: str):
        mode = str(mode or "fill").lower()
        if mode not in {"fit", "fill", "original"}:
            mode = "fill"
        self._display_mode = mode
        if isinstance(self.source, dict):
            self.source["display_mode"] = mode

    @property
    def display_mode(self) -> str:
        return self._display_mode

    def set_frame(self, image: QImage):
        if image.isNull():
            return
        self.set_loading(False)
        image = self.body.crop_image(image)
        pixmap = QPixmap.fromImage(image)
        target = self.body.size()
        if target.width() > 1 and target.height() > 1:
            # Smooth scaling on every frame is expensive with 9/16 simultaneous
            # tiles. Use fast preview scaling in mosaics and smooth interpolation
            # for a single focused view. Display modes never alter the RTSP source
            # or recorded resolution; they only change presentation inside the tile.
            transform = Qt.SmoothTransformation if self._dense_count <= 1 else Qt.FastTransformation
            if self._display_mode == "fill":
                expanded = pixmap.scaled(target, Qt.KeepAspectRatioByExpanding, transform)
                x = max(0, (expanded.width() - target.width()) // 2)
                y = max(0, (expanded.height() - target.height()) // 2)
                width = min(target.width(), expanded.width())
                height = min(target.height(), expanded.height())
                pixmap = expanded.copy(x, y, width, height)
            elif self._display_mode == "original":
                # Never upscale in 1:1 mode. If the source is larger than the tile,
                # crop centrally so QLabel geometry remains stable.
                if pixmap.width() > target.width() or pixmap.height() > target.height():
                    x = max(0, (pixmap.width() - target.width()) // 2)
                    y = max(0, (pixmap.height() - target.height()) // 2)
                    pixmap = pixmap.copy(x, y, min(target.width(), pixmap.width()), min(target.height(), pixmap.height()))
            else:
                pixmap = pixmap.scaled(target, Qt.KeepAspectRatio, transform)
        self.body.setText("")
        self.body.setPixmap(pixmap)



class DetachedMonitorWindow(QMainWindow):
    """Independent Live View workspace for multi-monitor operation.

    It shares Sites/inventory/keyring with the main window, but owns its own
    mosaic, FFmpeg sessions, selection and reconnect lifecycle.
    """
    closed = Signal(str)

    def __init__(self, controller, window_key: str, state: dict | None = None):
        super().__init__(controller)
        self.controller = controller
        self.db = controller.db
        self.window_key = str(window_key)
        self.site_id = int(controller.current_site_id or 0)
        self.sessions = {}
        self._streams_suspended = False
        self.audio_session = None
        self.audio_tile_index = None
        self.audio_volume = int(getattr(controller, "live_audio_volume", 75) or 75)
        self.video_tiles = []
        self.selected_tile = None
        self._individual_fullscreen_tile = None
        self._individual_return_fullscreen = False
        self._restore_geometry = None
        self.setWindowTitle(f"Artin Sentinel — Monitoramento {self.window_key}")
        self.setWindowIcon(QIcon(resource_path("artin-sentinel.png")))
        self.resize(1180, 760)
        self.setMinimumSize(760, 480)

        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(6,6,6,6); outer.setSpacing(6)
        self.toolbar_widget = QWidget(); tb = QHBoxLayout(self.toolbar_widget); tb.setContentsMargins(0,0,0,0)
        title = QLabel("JANELA DE MONITORAMENTO"); title.setStyleSheet("font-weight:700")
        tb.addWidget(title); tb.addStretch(); tb.addWidget(QLabel("Mosaico"))
        self.layout_combo = QComboBox()
        for count in SUPPORTED_GRID_COUNTS:
            self.layout_combo.addItem(str(count), count)
        self.layout_combo.currentIndexChanged.connect(self.change_layout)
        tb.addWidget(self.layout_combo)
        fs = QToolButton(); fs.setObjectName("ToolbarIconAction"); fs.setToolTip("Tela cheia do mosaico")
        try: fs.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        except Exception: fs.setText("⛶")
        fs.clicked.connect(self.toggle_mosaic_fullscreen); tb.addWidget(fs)
        outer.addWidget(self.toolbar_widget)

        self.splitter = QSplitter(Qt.Horizontal); self.splitter.setChildrenCollapsible(False)
        self.source_frame = QFrame(); self.source_frame.setObjectName("SourcePane"); self.source_frame.setMinimumWidth(220); self.source_frame.setMaximumWidth(320)
        sl = QVBoxLayout(self.source_frame); sl.setContentsMargins(8,8,8,8)
        sl.addWidget(QLabel("SITES / EQUIPAMENTOS / CANAIS"))
        self.source_tree = QTreeWidget(); self.source_tree.setHeaderHidden(True)
        from .brand_tree import install as install_brand_delegate
        install_brand_delegate(self.source_tree)
        self.source_tree.itemClicked.connect(self.source_clicked)
        self.source_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.source_tree.customContextMenuRequested.connect(self.source_context_menu)
        sl.addWidget(self.source_tree, 1)
        self.splitter.addWidget(self.source_frame)
        self.video_host = QWidget(); self.grid = QGridLayout(self.video_host); self.grid.setContentsMargins(0,0,0,0); self.grid.setSpacing(4)
        self.splitter.addWidget(self.video_host); self.splitter.setStretchFactor(1,1)
        outer.addWidget(self.splitter, 1)
        self.status = QLabel("Janela independente • somente leitura"); self.status.setStyleSheet("color:#7e998d;font-size:10px")
        outer.addWidget(self.status)

        self.poll_timer = QTimer(self); self.poll_timer.setInterval(80); self.poll_timer.timeout.connect(self.poll_streams); self.poll_timer.start()
        self.refresh_sources()
        state = state or {}
        count = int(state.get("grid_count") or 4)
        idx = self.layout_combo.findData(count); self.layout_combo.blockSignals(True); self.layout_combo.setCurrentIndex(max(0,idx)); self.layout_combo.blockSignals(False)
        self.rebuild_grid(count)
        for i, source in enumerate(state.get("slots") or []):
            if i < len(self.video_tiles) and source:
                self.apply_source(self.video_tiles[i], source)
        self.visibility_timer = QTimer(self)
        self.visibility_timer.setInterval(1000)
        self.visibility_timer.timeout.connect(self._sync_stream_visibility)
        self.visibility_timer.start()
        geometry = state.get("geometry") or {}
        if geometry:
            try: self.setGeometry(int(geometry.get("x",100)), int(geometry.get("y",100)), int(geometry.get("w",1180)), int(geometry.get("h",760)))
            except Exception: pass
        screen_name = state.get("screen_name") or ""
        if screen_name and screen_name not in {sc.name() for sc in QApplication.screens()}:
            primary = QApplication.primaryScreen()
            if primary:
                rect = primary.availableGeometry(); self.move(rect.center() - self.rect().center())
        if state.get("fullscreen"):
            QTimer.singleShot(150, self.showFullScreen)

    def refresh_sources(self):
        self.source_tree.clear(); site_map = {}
        for site in self.db.list_sites():
            item = QTreeWidgetItem([site["name"]]); item.setData(0, Qt.UserRole, ("site", site["id"])); self.source_tree.addTopLevelItem(item); site_map[int(site["id"])] = item
        for dev in self.db.list_devices(None):
            parent = site_map.get(int(dev["site_id"]))
            if parent is None: continue
            from .device_intelligence import device_tree_label
            di = QTreeWidgetItem([device_tree_label(dev)]); di.setData(0, Qt.UserRole, ("device", dev["id"])); parent.addChild(di)
            from .brand_tree import decorate_device_item
            decorate_device_item(di,dev)
            # The source tree is an inventory view, not a transient health filter.
            # Keep known recorder channels visible even when the latest probe marked
            # them unavailable; opening/health logic will expose their current state.
            for ch in self.db.list_recorder_channels(dev["id"]):
                ci = QTreeWidgetItem([self.db.channel_display_name(ch)])
                ci.setIcon(0, status_dot_icon("channel" if ch["available"] else "unknown", 7))
                ci.setData(0, Qt.UserRole, ("channel", dev["id"], ch["id"]))
                di.addChild(ci)
        self.source_tree.expandAll()

    def rebuild_grid(self, count: int):
        if self._individual_fullscreen_tile is not None:
            self._exit_camera_fullscreen()
        existing = {t.index: dict(t.source) for t in self.video_tiles if t.source}
        self.stop_all()
        while self.grid.count():
            item = self.grid.takeAt(0); w = item.widget();
            if w: w.deleteLater()
        for idx in range(20):
            self.grid.setRowStretch(idx,0); self.grid.setColumnStretch(idx,0)
        self.video_tiles=[]; self.selected_tile=None
        cols=int(ceil(sqrt(max(1,count)))); rows=int(ceil(count/cols))
        for i in range(count):
            tile=VideoTile(i); tile.set_dense_mode(count); tile.activated.connect(self.select_tile); tile.doubleActivated.connect(self.toggle_camera_fullscreen); tile.closeRequested.connect(self.close_tile)
            tile.audioRequested.connect(self.toggle_audio); tile.talkRequested.connect(self.show_talkback); tile.moveRequested.connect(self.move_tile_source)
            tile.setContextMenuPolicy(Qt.CustomContextMenu); tile.customContextMenuRequested.connect(lambda pos,t=tile:self.tile_context_menu(t,pos))
            r,c=divmod(i,cols); self.grid.addWidget(tile,r,c); self.video_tiles.append(tile)
        for r in range(rows): self.grid.setRowStretch(r,1)
        for c in range(cols): self.grid.setColumnStretch(c,1)
        if self.video_tiles: self.select_tile(self.video_tiles[0])
        for idx,src in existing.items():
            if idx < len(self.video_tiles): self.apply_source(self.video_tiles[idx],src)
        self.save_state()

    def change_layout(self): self.rebuild_grid(int(self.layout_combo.currentData() or 4))
    def select_tile(self,tile):
        for c in self.video_tiles: c.set_selected(c is tile)
        self.selected_tile=tile

    def move_tile_source(self, source_tile, global_pos):
        if source_tile is None or not source_tile.source:
            return
        target = next((t for t in self.video_tiles if t is not source_tile and t.rect().contains(t.mapFromGlobal(global_pos))), None)
        if target is None:
            return
        a, b = source_tile.index, target.index
        source_tile.swap_content_with(target)
        sa = self.sessions.pop(a, None); sb = self.sessions.pop(b, None)
        if sa is not None: self.sessions[b] = sa
        if sb is not None: self.sessions[a] = sb
        if self.audio_tile_index == a:
            self.audio_tile_index = b
        elif self.audio_tile_index == b:
            self.audio_tile_index = a
        for t in self.video_tiles:
            t.set_audio_active(self.audio_tile_index == t.index)
        self.select_tile(target)
        self.status.setText(f"Canal movido: janela {a + 1} → {b + 1}")
        self.save_state()

    def _stream_choice(self, ch, forced=None):
        from .hik_sdk import live_choice
        choice=live_choice(self.db.get_device(ch["device_id"]),ch["channel_no"],forced or ch["preferred_stream"]) if getattr(self,"db",None) is not None else None
        if choice is not None:return choice
        pref=forced or ch["preferred_stream"] or "auto"; main=ch["main_rtsp_url"] or ch["rtsp_url"]; sub=ch["sub_rtsp_url"] or ""
        if pref=="main": return ("main",main,"","") if main else ("sub",sub,"","")
        if pref=="sub": return ("sub",sub,"","") if sub else ("main",main,"","")
        keys=set(ch.keys()) if hasattr(ch,"keys") else set(); route=str(ch["route_kind"] or "") if "route_kind" in keys else "via_recorder"; kind=str(ch["channel_kind"] or "") if "channel_kind" in keys else "unknown"; last=str(ch["last_good_stream"] or "") if "last_good_stream" in keys else ""
        if route=="via_recorder" and kind=="ip" and last in {"main","sub"}:
            pu=main if last=="main" else sub; fk="sub" if last=="main" else "main"; fu=sub if last=="main" else main
            if pu:return last,pu,fk if fu else "",fu
        if len(self.video_tiles)==1: pk,pu,fk,fu="main",main,"sub",sub
        else: pk,pu,fk,fu="sub",sub,"main",main
        if not pu: pk,pu,fk,fu=fk,fu,"",""
        return pk,pu,fk,fu

    def _fps(self):
        n=len(self.video_tiles)
        return 10 if n<=16 else 8 if n<=36 else 5 if n<=64 else 3

    def apply_source(self,tile,source):
        if getattr(self, "_closed", False) or tile not in self.video_tiles:
            return
        self.stop_tile(tile)
        dev=self.db.get_device(int(source.get("device_id",0))); ch=self.db.get_recorder_channel(int(source.get("channel_id",0)))
        if not dev or not ch: tile.set_source("Canal","Fonte não encontrada","Atualize a janela",source); return
        title=self.db.channel_display_name(ch); route_kind=(ch["route_kind"] if "route_kind" in ch.keys() else "via_recorder")
        if not bool(ch["available"]) and not recoverable_native_channel(dev, ch) and (route_kind == "direct" or resolve_operational_identity(dev).kind == "nvr"):
            tile.set_source(title, "Vídeo ainda não confirmado", "Consulte Canais / Stream e a coluna Evidência", source)
            return
        mode,url,fmode,furl=self._stream_choice(ch,source.get("forced_stream")); src=dict(source); src.update({"type":"channel","title":title,"active_stream":mode})
        route="Direta" if route_kind == "direct" else f"Via {dev['name']}"
        transport_label = ("Cloud via Wine" if str(url or "").lower().startswith("intelbras-wine://") else "Cloud via ponte" if str(url or "").lower().startswith("intelbras-cloud://")
                           else "Hikvision SDK local" if str(url or "").lower().startswith("hik-sdk://") else "DVRIP" if str(url or "").lower().startswith("dvrip://") else "RTSP")
        tile.set_source(title,f"{route}\nConectando…",f"{mode} • {transport_label}",src)
        audio_info = channel_audio_info(dev, ch)
        if str(url).startswith("hik-sdk:"):audio_info={"can_listen":False,"can_talk":False,"label":"Áudio SDK em validação"}
        talk_reason = str(audio_info.get("talkback_netsdk_runtime") or "") if audio_info.get("talkback_pending") else ""
        if audio_info.get("talkback_pending") and not talk_reason:
            talk_reason = "MIC indisponível neste canal • transporte de retorno ainda não homologado"
        tile.set_audio_capabilities(
            bool(audio_info["can_listen"] or audio_info.get("can_probe_listen")), audio_info["can_talk"],
            active=(self.audio_tile_index == tile.index), label=audio_info["label"],
            talk_pending=bool(audio_info.get("talkback_pending")), talk_reason=talk_reason,
        )
        if not url: tile.body.setText("Stream não disponível neste perfil"); return
        creds=self.controller._credentials_for_device(int(dev["id"]))
        if not creds: tile.body.setText("Credencial necessária. Configure/teste o equipamento na janela principal."); return
        user,pwd=creds; sess=create_live_stream_session(url,user,pwd,fps=self._fps(),profile_name=("Main stream" if mode=="main" else "Substream"),fallback_url=furl,fallback_name=("Main stream" if fmode=="main" else "Substream") if fmode else "",stop_after_initial_failures=3 if route_kind=="direct" else 0,transport_fallback=(route_kind=="direct" and not str(url or "").lower().startswith("dvrip://")))
        if uses_hikvision_recordings(dev) and mode=='main':sess.frame_width=1280;sess.frame_height=720
        self.sessions[tile.index]=sess; sess.start(); tile.set_loading(True); self.save_state()

    def stop_tile(self,tile):
        tile.set_loading(False)
        sess=self.sessions.pop(tile.index,None)
        if sess: sess.stop()
        if self.audio_tile_index == tile.index: self.stop_audio()
    def stop_all(self):
        for tile in getattr(self, "video_tiles", ()): tile.set_loading(False)
        vals=list(self.sessions.values()); self.sessions.clear()
        for s in vals: s.stop()
        self.stop_audio()
    def _sync_stream_visibility(self):
        if getattr(self, "_closed", False):
            return
        hidden = not self.isVisible() or self.isMinimized()
        if hidden and not self._streams_suspended:
            self._streams_suspended = True
            self.stop_all()
            self.poll_timer.stop()
            self.status.setText("Vídeos pausados • janela oculta ou minimizada")
        elif not hidden and self._streams_suspended:
            self._streams_suspended = False
            for tile in list(self.video_tiles):
                if tile.source and tile.source.get("type") == "channel":
                    self.apply_source(tile, dict(tile.source))
            self.poll_timer.start()
            self.status.setText("Monitoramento retomado")
    def close_tile(self,tile):
        focused = self._individual_fullscreen_tile is tile
        closed_index = tile.index
        self.stop_tile(tile)
        tile.clear_source()
        if focused:
            self._exit_camera_fullscreen(select_fallback=True, closed_index=closed_index)
        self.save_state()

    def source_clicked(self,item,_col):
        data=item.data(0,Qt.UserRole)
        if not data:return
        if data[0]=="device": self.open_all(int(data[1])); return
        if data[0]!="channel":return
        if self.selected_tile is None and self.video_tiles:self.select_tile(self.video_tiles[0])
        tile=self.selected_tile
        if tile is None:return
        src={"type":"channel","device_id":int(data[1]),"channel_id":int(data[2])}; self.apply_source(tile,src)
        start=tile.index; next_idx=next_empty_slot([t.source for t in self.video_tiles],start)
        if next_idx is not None:self.select_tile(self.video_tiles[next_idx])

    def open_all(self,device_id):
        dev = self.db.get_device(int(device_id))
        if not dev:return
        all_channels = self.db.list_recorder_channels(int(device_id))
        identity = resolve_operational_identity(dev)
        channels = channels_for_live_view(all_channels, identity.kind)
        channels += [ch for ch in all_channels if ch not in channels and not bool(ch["available"]) and recoverable_native_channel(dev, ch)]
        if not channels:
            if all_channels and identity.kind == "nvr":
                self.status.setText("NVR sem vídeo confirmado • consulte Canais / Stream na janela principal")
            return
        needed=sum(1 for t in self.video_tiles if t.source)+len(channels); target=smallest_grid_for(needed)
        if target>len(self.video_tiles):
            idx=self.layout_combo.findData(target); self.layout_combo.blockSignals(True); self.layout_combo.setCurrentIndex(max(0,idx)); self.layout_combo.blockSignals(False); self.rebuild_grid(target)
        empties=[t for t in self.video_tiles if not t.source]
        for ch,tile in zip(channels,empties): self.apply_source(tile,{"type":"channel","device_id":device_id,"channel_id":int(ch["id"])})
        self.save_state()

    def source_context_menu(self,pos):
        item=self.source_tree.itemAt(pos)
        if not item:return
        data=item.data(0,Qt.UserRole); menu=QMenu(self)
        if data and data[0]=="device":
            a=menu.addAction("Abrir todos os canais"); a.triggered.connect(lambda:self.open_all(int(data[1])))
        elif data and data[0]=="channel":
            for label,mode in (("Automático","auto"),("Substream","sub"),("Main stream","main")):
                a=menu.addAction(label); a.triggered.connect(lambda _=False,m=mode,d=data:self.open_channel_mode(int(d[1]),int(d[2]),m))
        menu.popup(self.source_tree.viewport().mapToGlobal(pos)); self._menu=menu

    def open_channel_mode(self,device_id,channel_id,mode):
        if self.selected_tile is None and self.video_tiles:self.select_tile(self.video_tiles[0])
        if self.selected_tile:self.apply_source(self.selected_tile,{"type":"channel","device_id":device_id,"channel_id":channel_id,"forced_stream":mode})

    def tile_context_menu(self,tile,pos):
        self.select_tile(tile); menu=QMenu(self)
        if tile.source:
            sm=menu.addMenu("Stream")
            active_kind=str(tile.source.get("active_stream") or "")
            for label,mode in (("Automático","auto"),("Substream","sub"),("Main stream","main")):
                shown=("● "+label) if mode==active_kind else label
                a=sm.addAction(shown); a.triggered.connect(lambda _=False,m=mode,t=tile:self.change_tile_stream(t,m))
            fm=menu.addMenu("Enquadramento")
            for label,mode in (("Preencher (sem esticar)","fill"),("Ajustar / imagem inteira","fit"),("Original / 1:1","original")):
                shown=("● "+label) if tile.display_mode==mode else label
                a=fm.addAction(shown); a.triggered.connect(lambda _=False,m=mode,t=tile:self.change_tile_display_mode(t,m))
            fs=menu.addAction("Tela cheia desta câmera"); fs.triggered.connect(lambda:self.toggle_camera_fullscreen(tile))
            stop=menu.addAction("Parar reconexão"); stop.triggered.connect(lambda:self.stop_tile(tile))
            menu.addSeparator()
        close=menu.addAction("Fechar canal"); close.triggered.connect(lambda:self.close_tile(tile))
        menu.popup(tile.mapToGlobal(pos)); self._tile_menu=menu

    def change_tile_stream(self,tile,mode):
        if not tile.source:return
        listening = self.audio_tile_index == tile.index and self.audio_session is not None
        src=dict(tile.source); src["forced_stream"]=mode if mode!="auto" else ""; self.apply_source(tile,src)
        if listening and tile.index in self.sessions:
            self.toggle_audio(tile)

    def change_tile_display_mode(self, tile, mode):
        tile.set_display_mode(mode)
        if isinstance(tile.source, dict):
            tile.source["display_mode"] = tile.display_mode
        self.status.setText({"fill":"Enquadramento: Preencher","fit":"Enquadramento: Ajustar","original":"Enquadramento: Original / 1:1"}.get(tile.display_mode,"Enquadramento atualizado"))
        self.save_state()

    def _audio_context(self, tile):
        if not tile or not tile.source:
            return None
        dev=self.db.get_device(int(tile.source.get("device_id",0))); ch=self.db.get_recorder_channel(int(tile.source.get("channel_id",0)))
        if not dev or not ch:
            return None
        info=channel_audio_info(dev,ch); active=tile.source.get("active_stream") or "sub"
        urls=ordered_audio_urls(ch["main_rtsp_url"] or "", ch["sub_rtsp_url"] or "", ch["rtsp_url"] or "", active)
        return dev,ch,info,urls

    def stop_audio(self):
        sess=self.audio_session; self.audio_session=None; self.audio_tile_index=None
        if sess is not None:
            self._previous_audio_session = sess
        if sess: sess.stop()
        for t in self.video_tiles: t.set_audio_active(False)

    def toggle_audio(self,tile):
        if self.audio_tile_index==tile.index and self.audio_session:
            self.stop_audio(); return
        ctx=self._audio_context(tile)
        if not ctx: return
        dev,ch,info,urls=ctx
        if (not info["can_listen"] and not info.get("can_probe_listen")) or not urls:
            tile.set_audio_active(False); return
        creds=self.controller._credentials_for_device(int(dev["id"]))
        if not creds:
            tile.set_audio_active(False); return
        previous_audio = self.audio_session or getattr(self, "_previous_audio_session", None)
        self.stop_audio(); user,pwd=creds
        self.audio_session=create_live_audio_session(
            urls, user, pwd, volume=self.audio_volume, previous_session=previous_audio,
            audio_confirmed=bool(info.get("can_listen")),
            audio_codec=str(ch["audio_codec"] or ""),
            audio_sample_rate=int(ch["audio_sample_rate"] or 0),
        ); self._previous_audio_session = None
        self.audio_tile_index=tile.index; tile.set_audio_active(True); self.audio_session.start()

    def show_talkback(self,tile):
        ctx=self._audio_context(tile)
        if not ctx or not ctx[2]["can_talk"]: return
        info = ctx[2]
        if str(info.get("talkback_protocol") or "") == "xm-dvrip-g711a-experimental":
            QMessageBox.information(
                self, "Push-to-Talk",
                "O MIC experimental está disponível para este canal na janela principal. "
                "A janela independente permanece com escuta; selecione a mesma câmera no Live View principal para escolher/testar o microfone e usar o PTT.",
            )
            return
        QMessageBox.information(self,"Push-to-Talk","Capacidade bidirecional conhecida, mas o transporte de retorno deste provider ainda não está disponível nesta janela.")

    def poll_streams(self):
        if getattr(self, "_closed", False):
            return
        for tile in list(self.video_tiles):
            sess=self.sessions.get(tile.index)
            tile.sync_loading(sess)
            if not sess: continue
            status=sess.latest_status()
            if status:
                tile.footer.setText(f"{status} • {sess.active_profile}")
                active_kind = "main" if sess.active_profile.lower().startswith("main") else "sub"
                if tile.source: tile.source["active_stream"] = active_kind
                tile.set_stream_indicator(active_kind)
            frame=sess.latest_frame()
            if frame is not None:
                img=QImage(frame.pixels,frame.width,frame.height,frame.width*3,QImage.Format_RGB888).copy(); tile.set_frame(img)
                tile.update_media_badge(sess)
                if tile.source and isinstance(sess, (DvripLiveStreamSession, IntelbrasCloudLiveSession)) and not getattr(sess, "_inventory_frame_confirmed", False):
                    try:
                        sess._inventory_frame_confirmed = self.db.confirm_native_channel_frame(int(tile.source.get("channel_id",0)), route=getattr(sess,"active_url",sess.url))
                    except Exception:
                        pass
                if tile.source and not tile.source.get("_last_good_saved"):
                    active_kind = "main" if sess.active_profile.lower().startswith("main") else "sub"
                    try:
                        self.db.update_channel_last_good_stream(int(tile.source.get("channel_id",0)), active_kind)
                        tile.source["_last_good_saved"] = active_kind
                    except Exception:
                        pass
        if self.audio_session is not None:
            status=self.audio_session.latest_status()
            if status:
                if self.audio_tile_index is not None and 0 <= self.audio_tile_index < len(self.video_tiles):
                    atile=self.video_tiles[self.audio_tile_index]; title=(atile.header.text() or f"Janela {self.audio_tile_index+1}")
                    if status.startswith("🔊 Áudio ativo"):
                        self.status.setText(f"Áudio: {title}")
                    else:
                        self.status.setText(f"Áudio: {title} • {status.replace('Áudio:', '').strip()}")
                else:
                    self.status.setText(status)
            if self.audio_tile_index is not None and 0 <= self.audio_tile_index < len(self.video_tiles):
                atile=self.video_tiles[self.audio_tile_index]
                if self.audio_session.detected_codec and atile.source:
                    try:
                        cid=int(atile.source.get("channel_id",0)); current=self.db.get_recorder_channel(cid)
                        if current and (str(current["audio_codec"] or "") != str(self.audio_session.detected_codec) or str(current["audio_mode"] or "") != "listen"):
                            self.db.update_channel_audio(cid,"listen",str(self.audio_session.detected_codec),int(self.audio_session.detected_sample_rate or 0),int(current["audio_channels"] or 0),"Áudio validado na janela de monitoramento")
                    except Exception:
                        pass
            if self.audio_session.finished:
                for t in self.video_tiles: t.set_audio_active(False)
                self.audio_tile_index = None
                self.audio_session = None

    def _exit_camera_fullscreen(self, *, select_fallback: bool = False, closed_index: int | None = None):
        was_fullscreen = bool(getattr(self, "_individual_return_fullscreen", False))
        self._individual_fullscreen_tile = None
        self._individual_return_fullscreen = False
        for t in self.video_tiles:
            t.show()
            t.set_dense_mode(len(self.video_tiles))
        self.source_frame.show(); self.toolbar_widget.show(); self.status.show()
        if was_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
        if select_fallback and self.video_tiles:
            start = int(closed_index if closed_index is not None else -1)
            candidates = [t for t in self.video_tiles if t.index != start and t.source]
            if not candidates:
                candidates = [t for t in self.video_tiles if t.index != start]
            if not candidates and self.video_tiles:
                candidates = [self.video_tiles[0]]
            if candidates:
                self.select_tile(candidates[0])

    def toggle_camera_fullscreen(self,tile):
        if not tile.source:return
        if self._individual_fullscreen_tile is tile:
            self._exit_camera_fullscreen(); return
        self._individual_return_fullscreen = bool(self.isFullScreen() and self._individual_fullscreen_tile is None)
        self._individual_fullscreen_tile=tile
        for t in self.video_tiles:t.setVisible(t is tile)
        tile.set_dense_mode(1)
        self.source_frame.hide(); self.toolbar_widget.hide(); self.status.hide(); self.showFullScreen()

    def toggle_mosaic_fullscreen(self):
        if self.isFullScreen() and self._individual_fullscreen_tile is None:self.showNormal()
        else:self.showFullScreen()

    def save_state(self):
        if not self.site_id:return
        slots=[]
        for t in self.video_tiles:
            src=t.source or {}
            slots.append({"type":"channel","device_id":src.get("device_id"),"channel_id":src.get("channel_id"),"forced_stream":src.get("forced_stream",""),"display_mode":src.get("display_mode",t.display_mode)} if src.get("type")=="channel" else {})
        g=self.geometry(); screen=self.screen().name() if self.screen() else ""
        self.db.save_live_window(self.site_id,self.window_key,self.windowTitle(),screen,{"x":g.x(),"y":g.y(),"w":g.width(),"h":g.height()},len(self.video_tiles) or 4,slots,self.isFullScreen(),True)

    def closeEvent(self,event):
        self._closed = True
        self.visibility_timer.stop()
        sessions = media_session_chain(list(self.sessions.values()) + [
            self.audio_session, getattr(self, "_previous_audio_session", None)])
        self.save_state(); self.stop_all(); self.poll_timer.stop()
        if not getattr(self.controller, "_closing_app", False):
            wait_media_sessions(sessions, timeout=1.5)
        if not getattr(self.controller, "_closing_app", False):
            try: self.db.disable_live_window(self.site_id, self.window_key)
            except Exception: pass
        self.closed.emit(self.window_key); super().closeEvent(event)


class ZoomImageLabel(QLabel):
    clicked = Signal()
    doubleClicked = Signal(int)

    def __init__(self, index: int, text: str):
        super().__init__(text)
        self.index = index
        self.zoom_factor = 1.0
        self.zoom_x = self.zoom_y = 0.5
        self._pan_origin = None
        self.setToolTip("Roda: ampliar/reduzir • arraste: mover • botão direito: restaurar")

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.zoom_x = self.zoom_y = 0.5

    def crop_image(self, image: QImage) -> QImage:
        if self.zoom_factor <= 1 or image.isNull():
            return image
        width = max(1, round(image.width() / self.zoom_factor))
        height = max(1, round(image.height() / self.zoom_factor))
        x = max(0, min(image.width() - width, round(self.zoom_x * image.width() - width / 2)))
        y = max(0, min(image.height() - height, round(self.zoom_y * image.height() - height / 2)))
        return image.copy(x, y, width, height)

    def wheelEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return super().wheelEvent(event)
        self.zoom_factor = max(1.0, min(8.0, self.zoom_factor * (1.25 ** (event.angleDelta().y() / 120))))
        if self.zoom_factor == 1:
            self.zoom_x = self.zoom_y = 0.5
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.reset_zoom()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            if self.zoom_factor > 1:
                self._pan_origin = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None and self.zoom_factor > 1:
            delta = event.position().toPoint() - self._pan_origin
            self.zoom_x = max(0.0, min(1.0, self.zoom_x - delta.x() / max(1, self.width())))
            self.zoom_y = max(0.0, min(1.0, self.zoom_y - delta.y() / max(1, self.height())))
            self._pan_origin = event.position().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.index)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class PlaybackScreen(ZoomImageLabel):
    def __init__(self, index, text):
        super().__init__(index, text)
        self._source_image = None

    def set_frame(self, image):
        self._source_image = image
        QLabel.setText(self, "")
        self._render_frame()

    def _render_frame(self):
        image = getattr(self, '_source_image', None)
        if image is None or image.isNull() or self.width() < 2 or self.height() < 2:
            return
        transform = Qt.FastTransformation if self.property('dense_preview') else Qt.SmoothTransformation
        QLabel.setPixmap(self, QPixmap.fromImage(self.crop_image(image)).scaled(self.size(), Qt.KeepAspectRatio, transform))

    def setPixmap(self, pixmap):
        self._source_image = None
        super().setPixmap(pixmap)

    def setText(self, text):
        self._source_image = None
        super().setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_frame()

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self._render_frame()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._render_frame()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.zoom_factor > 1: self._render_frame()



class MainWindow(QMainWindow, CameraEventUi):
    PAGE_LIVE = 0
    PAGE_PLAYBACK = 1
    PAGE_CONFIG = 2
    # Internal destinations open their corresponding Configuration tab.
    PAGE_EVENTS = 3
    PAGE_HEALTH = 4

    def __init__(self):
        super().__init__()
        from .ui_metrics import UiMetrics
        self._ui_metrics = UiMetrics()
        self._ui_heartbeat = QTimer(self)
        self._ui_heartbeat.setInterval(250)
        self._ui_heartbeat.timeout.connect(self._ui_metrics.heartbeat)
        self._ui_heartbeat.start()
        self.app_auth = AppAuth(data_dir() / "access.json")
        self.access_control = AccessControl(data_dir())
        self.setWindowTitle(f"Artin Sentinel {__version__}")
        self.setWindowIcon(QIcon(resource_path("artin-sentinel.png")))
        self.resize(1460, 900)
        self.setMinimumSize(1100, 700)

        self.db = Database(data_dir() / "sentinel.db")
        self.db.normalize_known_device_classification()
        self.pool = QThreadPool.globalInstance()
        # Recorder onboarding intentionally avoids Qt worker signals. On Fedora 44
        # with Python 3.14/PySide6 6.11 we observed a native Shiboken crash while
        # a nested QDialog event loop was active. A plain Python executor + GUI
        # polling keeps all Qt object access strictly on the main thread.
        self.recorder_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-recorder")
        self.ptz_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-ptz")
        self.audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-audio-input")
        self.ptz_results = Queue()
        self.current_site_id = None
        self.discovery_seconds = 0
        self.discovery_results = []
        self.session_credentials = {}
        self.credential_store = CredentialStore()
        self.credential_save_notice = ""
        self.channel_scan_context = None
        self.channel_scan_cancel_event = None
        self.channel_scan_worker = None
        self.channel_scan_future = None
        self.channel_scan_progress_queue = None
        self.recorder_credentials_dialog = None
        self.recorder_credentials_inputs = None
        self._monitor_paused_for_recorder = False
        self.channel_health_inflight = set()
        self.channel_health_last_started = {}
        self._transient_dialogs = []
        self.qt_workers = set()
        self.video_tiles = []
        self.selected_video_tile = None
        self.live_sessions = {}
        self.live_audio_session = None
        self.live_audio_tile_index = None
        self.live_audio_volume = 75
        self.live_audio_identity = ""
        self.audio_input_preferences = load_audio_input_preferences(data_dir())
        self.ui_settings = QSettings("Artin", "Artin Sentinel")
        self.microphone_inputs: list[MicrophoneInput] = []
        self.microphone_scan_future = None
        self.microphone_scan_complete = False
        self.microphone_test_future = None
        self.netsdk_install_future = None
        self.talkback_session = None
        self.talkback_tile_index = None
        self.mic_traces = {}
        self._talkback_resume_audio = False
        self.selected_channel_context = None
        self._stream_combo_sync = False
        self._workspace_restored_site = None
        self._workspace_restore_pending = False
        self.live_diag_lines = {}
        self.detached_windows = {}
        self._detached_window_seq = 0
        self._primary_mosaic_fullscreen = False
        self._focus_return_state = None
        self._closing_app = False
        self.manual_recording = None
        self.update_settings = load_update_settings(data_dir())
        self.akdb_sync_settings = load_akdb_sync_settings(data_dir())
        self.akdb_remote_result = None
        self.akdb_sync_worker = None
        self.akdb_apply_worker = None
        self.akdb_submit_worker = None
        self.available_update = None
        self.staged_update = None
        self.update_worker = None
        self.update_install_worker = None
        self.playback_search_worker = None
        self.playback_session = None
        self.playback_sessions = {}
        self.playback_active_channels = ()
        self.playback_multi_recordings = ()
        self.playback_audio_session = None
        self.playback_audio_route = None
        self.playback_audio_candidates = {}
        self._playback_loaded_device_id = None
        self.playback_export_worker = None
        self.playback_export_cancel = None
        self.playback_clip_bounds = None
        self.playback_trim_start = None
        self.playback_trim_end = None
        self._update_in_progress = False
        self._ptz_active_direction = ""
        self._ptz_command_pending = False
        self.ptz_hold_timer = QTimer(self)
        self.ptz_hold_timer.setInterval(700)
        self.ptz_hold_timer.timeout.connect(self.renew_selected_ptz_hold)

        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self.topbar = self.build_topbar()
        main.addWidget(self.topbar)
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)

        self.build_live_page()
        self.build_playback_page()
        self.build_configuration_page()
        self.bottombar = self.build_bottombar()
        main.addWidget(self.bottombar)

        self.show_page(self.PAGE_LIVE)
        self.refresh_all()
        self.restore_live_workspace()
        self.restore_detached_windows()

        self.monitor = QTimer(self)
        self.monitor.timeout.connect(self.monitor_tick)
        self.monitor.start(30000)

        self.discovery_clock = QTimer(self)
        self.discovery_clock.timeout.connect(self.discovery_clock_tick)

        self.channel_scan_poll_timer = QTimer(self)
        self.channel_scan_poll_timer.setInterval(100)
        self.channel_scan_poll_timer.timeout.connect(self.poll_recorder_channel_scan)

        self.live_poll_timer = QTimer(self)
        self.live_poll_timer.setInterval(100)
        self.live_poll_timer.timeout.connect(lambda: self._ui_metrics.run("live", self.poll_live_streams))
        self.live_poll_timer.start()

        self.performance_label = QLabel("Streams: 0 • CPU: — • RAM: —")
        self.performance_label.setToolTip("Estimativa local do Sentinel e dos decodificadores FFmpeg ativos. CPU pode superar 100% em múltiplos núcleos.")
        self.statusBar().addPermanentWidget(self.performance_label)
        self.performance_samples = []
        performance_details = QToolButton(self)
        performance_details.setText("Medições")
        performance_details.setToolTip("Comparar CPU e RAM por tamanho do mosaico nesta sessão")
        performance_details.clicked.connect(self.show_performance_comparison)
        self.statusBar().addPermanentWidget(performance_details)
        self._performance_previous = None
        self.performance_timer = QTimer(self)
        self.performance_timer.setInterval(3000)
        self.performance_timer.timeout.connect(self.update_performance_indicator)
        self.performance_timer.start()

        self.ptz_poll_timer = QTimer(self)
        self.ptz_poll_timer.setInterval(120)
        self.ptz_poll_timer.timeout.connect(self.poll_ptz_results)
        self.ptz_poll_timer.start()
        # Microphone/FFmpeg enumeration can take seconds on some PipeWire hosts;
        # always discover it in a worker after the UI is alive.
        QTimer.singleShot(0, self.refresh_microphone_inputs_async)
        from .access_control_ui import sync_ui
        sync_ui(self)

    def start_qt_worker(self, worker):
        """Keep QRunnable/PySide wrappers alive until the worker finishes."""
        self.qt_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self.release_qt_worker(w))
        self.pool.start(worker)

    def release_qt_worker(self, worker):
        self.qt_workers.discard(worker)

    # ---------- chrome / navigation ----------
    def build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(68)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 7, 12, 7)
        layout.setSpacing(4)

        mark = QLabel()
        mark.setObjectName('BrandMark')
        mark.setStyleSheet('background:transparent;border:none;padding:0')
        pix = QPixmap(resource_path("artin-sentinel.png"))
        mark.setPixmap(pix.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mark.setFixedSize(50,50)
        layout.addWidget(mark)
        layout.addSpacing(8)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.setContentsMargins(0,0,0,0)
        brand.setAlignment(Qt.AlignVCenter)
        publisher=QLabel('ARTIN')
        publisher_font=QFont('Sans Serif',8)
        publisher_font.setWeight(QFont.DemiBold)
        publisher_font.setLetterSpacing(QFont.AbsoluteSpacing,2.6)
        publisher.setFont(publisher_font)
        publisher.setStyleSheet('font-family:Sans Serif;font-size:10px;font-weight:600;color:#93adb9;background:transparent;border:none;padding:0')
        title=QLabel('SENTINEL')
        title_font=QFont('Sans Serif',17)
        title_font.setWeight(QFont.DemiBold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing,.8)
        title.setFont(title_font)
        title.setStyleSheet('font-family:Sans Serif;font-size:22px;font-weight:600;color:#e8f4fa;background:transparent;border:none;padding:0')
        brand.addWidget(publisher)
        brand.addWidget(title)
        layout.addLayout(brand)
        layout.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        items = [
            ("Ao vivo", self.PAGE_LIVE),
            ("Reprodução", self.PAGE_PLAYBACK),
            ("Configuração", self.PAGE_CONFIG),
        ]
        for text, index in items:
            button = QPushButton(text)
            button.setObjectName("TopNav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()
        self.top_site_label = QLabel("Site: —")
        self.top_site_label.setStyleSheet("color:#a8bdb4;padding:0 10px")
        layout.addWidget(self.top_site_label)
        self.monitor_badge = QLabel("● MONITORANDO")
        self.monitor_badge.setStyleSheet(
            "color:#63d69d;background:#18352e;border:1px solid #3d7459;"
            "border-radius:10px;padding:5px 9px;font-size:11px;font-weight:600"
        )
        layout.addWidget(self.monitor_badge)
        return bar

    def build_bottombar(self):
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(30)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Keep persistent operational context in the status bar instead of
        # spending vertical space inside the Live View inspector.
        self.bottom_left = QLabel(f"Artin Sentinel {__version__}")
        self.bottom_left.setStyleSheet("color:#7e998d;font-size:11px")
        self.live_health_icon = self._standard_icon_label("SP_ComputerIcon", "Resumo do Site", 13)
        self.live_health = QLabel("Site: — · 0 equipamentos · 0 online")
        self.live_health.setStyleSheet("color:#90aa9e;font-size:11px")
        self.bottom_notice = QLabel("")
        self.bottom_notice.setStyleSheet("color:#809da8;font-size:11px")
        self.bottom_audio = QLabel("Áudio: desligado")
        self.bottom_audio.setStyleSheet("color:#90aa9e;font-size:11px")
        self.bottom_audio.setToolTip("Canal de áudio de escuta ativo")
        self.bottom_right = QLabel("Monitoramento: 30 s")
        self.bottom_right.setStyleSheet("color:#7e998d;font-size:11px")

        layout.addWidget(self.bottom_left)
        layout.addWidget(self.live_health_icon)
        layout.addWidget(self.live_health)
        layout.addWidget(self.bottom_notice)
        layout.addStretch()
        layout.addWidget(self.bottom_audio)
        layout.addWidget(self.bottom_right)
        return bar

    def show_page(self, index: int):
        if index==self.PAGE_PLAYBACK and not authorize(self,'playback'):return
        if index in (self.PAGE_EVENTS, self.PAGE_HEALTH):
            tab = self.events_page if index == self.PAGE_EVENTS else self.health_page
            self.config_tabs.setCurrentWidget(tab)
            index = self.PAGE_CONFIG
        self.pages.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button is not None:
            button.setChecked(True)

    # ---------- live / VMS workspace ----------
    def _toolbar_icon_button(self, standard_name: str, fallback: str, tooltip: str, handler):
        btn = QToolButton()
        btn.setObjectName("ToolbarIconAction")
        btn.setToolTip(tooltip)
        btn.setFixedSize(36, 34)
        try:
            pixmap = getattr(QStyle.StandardPixmap, standard_name)
            btn.setIcon(self._live_toolbar_icon(pixmap))
            btn.setIconSize(QSize(19, 19))
        except Exception:
            btn.setText(fallback)
        btn.clicked.connect(handler)
        btn.setAccessibleName(tooltip)
        return btn

    def _live_toolbar_icon(self, pixmap):
        return self._tinted_icon(pixmap, "#37c8e8")

    def _tinted_icon(self, pixmap, color):
        source = self.style().standardIcon(pixmap).pixmap(24, 24)
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color))
        painter.end()
        return QIcon(tinted)

    @staticmethod
    def _scissors_icon(color):
        canvas = QPixmap(24, 24)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), 1.8))
        painter.drawEllipse(2, 6, 7, 7)
        painter.drawEllipse(2, 15, 7, 7)
        painter.drawLine(9, 10, 21, 3)
        painter.drawLine(9, 18, 21, 23)
        painter.drawEllipse(11, 12, 2, 2)
        painter.end()
        return QIcon(canvas)

    def _standard_icon_label(self, standard_name: str, tooltip: str = "", size: int = 15):
        label = QLabel()
        label.setObjectName("SectionGlyph")
        label.setFixedSize(size + 2, size + 2)
        label.setAlignment(Qt.AlignCenter)
        if tooltip:
            label.setToolTip(tooltip)
        try:
            pixmap = getattr(QStyle.StandardPixmap, standard_name)
            label.setPixmap(self.style().standardIcon(pixmap).pixmap(size, size))
        except Exception:
            label.setText("•")
        return label

    def _set_live_selection_summary(self, title: str, meta: str = "", state: str = "", icon: str = "SP_ComputerIcon"):
        if not hasattr(self, "live_selection_title"):
            return
        self.live_selection_title.setText(title or "Nenhuma fonte selecionada")
        self.live_selection_meta.setText(meta or "Selecione uma câmera ou canal.")
        self.live_selection_meta.setVisible(bool(meta))
        if state:
            self.live_selection_status.setText(state.upper())
            self.live_selection_status.show()
            online = state.strip().lower() in {"online", "ao vivo", "live", "ativo"}
            self.live_selection_status.setStyleSheet(
                ("color:#63d69d;background:#18352e;border:1px solid #3d7459;"
                 "border-radius:7px;padding:2px 5px;font-size:8px;font-weight:700")
                if online else
                ("color:#aebdb6;background:#121b17;border:1px solid #2c3a34;"
                 "border-radius:7px;padding:2px 5px;font-size:8px;font-weight:700")
            )
        else:
            self.live_selection_status.hide()
        try:
            pixmap = getattr(QStyle.StandardPixmap, icon)
            self.live_selection_icon.setPixmap(self.style().standardIcon(pixmap).pixmap(22, 22))
        except Exception:
            self.live_selection_icon.setText("•")

    def build_live_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        label = QLabel("MONITORAMENTO AO VIVO")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        label.setFont(font)
        toolbar.addWidget(label)
        toolbar.addStretch()

        group = QFrame()
        group.setObjectName("LiveToolbarGroup")
        actions = QHBoxLayout(group)
        actions.setContentsMargins(8, 4, 8, 4)
        actions.setSpacing(6)
        caption = QLabel("MOSAICO")
        caption.setObjectName("LiveToolbarCaption")
        actions.addWidget(caption)
        self.layout_combo = QComboBox()
        self.layout_combo.setObjectName("LiveGridSelector")
        self.layout_combo.setToolTip("Layout do mosaico")
        for count in SUPPORTED_GRID_COUNTS:
            label = f"{count} câmera" if count == 1 else f"{count} câmeras"
            self.layout_combo.addItem(label, count)
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(4)))
        self.layout_combo.currentIndexChanged.connect(self.change_video_layout)
        self.layout_combo.setMaximumWidth(118)
        actions.addWidget(self.layout_combo)

        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("Rotina de observação: escolher e carregar um mosaico salvo")
        self.preset_combo.setMinimumWidth(120)
        self.preset_combo.setMaximumWidth(190)
        self.preset_combo.activated.connect(self.load_selected_live_preset)
        actions.addWidget(self.preset_combo)
        preset_menu = QToolButton()
        preset_menu.setObjectName("ToolbarIconAction")
        preset_menu.setText("⋯")
        preset_menu.setToolTip("Salvar ou excluir rotina de observação")
        preset_menu.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(preset_menu)
        menu.addAction("Salvar mosaico atual…", self.save_named_live_preset)
        menu.addAction("Excluir perfil selecionado…", self.delete_selected_live_preset)
        preset_menu.setMenu(menu)
        actions.addWidget(preset_menu)
        photo = self._toolbar_icon_button("SP_DialogSaveButton", "◉", "Salvar foto do canal selecionado", self.save_live_photo)
        actions.addWidget(photo)
        self.record_button = self._toolbar_icon_button("SP_MediaRecord", "●", "Iniciar gravação do canal selecionado", self.toggle_manual_recording)
        self.record_button.setIcon(QIcon())
        self.record_button.setText("●")
        actions.addWidget(self.record_button)

        self.inspector_toggle = QToolButton()
        self.inspector_toggle.setObjectName("ToolbarIconAction")
        self.inspector_toggle.setIcon(self._live_toolbar_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.inspector_toggle.setIconSize(QSize(19, 19))
        self.inspector_toggle.setFixedSize(36, 34)
        self.inspector_toggle.setToolTip("Mostrar ou recolher o painel lateral de controles")
        self.inspector_toggle.setAccessibleName("Mostrar ou recolher controles")
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.setChecked(str(self.ui_settings.value("live/inspector_visible", "true")).lower() not in ("false", "0"))
        self.inspector_toggle.toggled.connect(self.set_live_inspector_visible)
        actions.addWidget(self.inspector_toggle)

        # 0.2.18: compact VMS toolbar. Full text lives in tooltips instead of
        # consuming horizontal space over the mosaic.
        clear = self._toolbar_icon_button("SP_TrashIcon", "⌫", "Limpar mosaico", self.clear_video_grid_sources)
        actions.addWidget(clear)
        new_window = self._toolbar_icon_button(
            "SP_TitleBarNormalButton", "▣+", "Nova janela de monitoramento", self.new_monitor_window
        )
        actions.addWidget(new_window)
        full_mosaic = self._toolbar_icon_button(
            "SP_TitleBarMaxButton", "⛶", "Tela cheia do mosaico", self.toggle_primary_mosaic_fullscreen
        )
        actions.addWidget(full_mosaic)
        toolbar.addWidget(group)
        outer.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        source_frame = QFrame()
        self.live_source_frame = source_frame
        source_frame.setObjectName("SourcePane")
        source_frame.setMinimumWidth(235)
        source_frame.setMaximumWidth(340)
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(10, 10, 10, 10)
        source_title = QLabel("SITES / GRAVADORES / CÂMERAS")
        source_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px")
        source_layout.addWidget(source_title)
        self.source_filter = QLineEdit()
        self.source_filter.setPlaceholderText("Filtrar câmeras e canais…")
        self.source_filter.textChanged.connect(self.filter_source_tree)
        source_layout.addWidget(self.source_filter)
        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        from .brand_tree import install as install_brand_delegate
        install_brand_delegate(self.source_tree)
        self.source_tree.itemClicked.connect(self.source_single_clicked)
        self.source_tree.itemDoubleClicked.connect(self.source_double_clicked)
        self.source_tree.itemSelectionChanged.connect(self.source_selection_changed)
        self.source_tree.itemExpanded.connect(self._source_expansion_changed)
        self.source_tree.itemCollapsed.connect(self._source_expansion_changed)
        self.source_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.source_tree.customContextMenuRequested.connect(self.show_source_context_menu)
        source_layout.addWidget(self.source_tree, 1)
        hint = QLabel("Clique em um canal para abrir no slot selecionado; clique no gravador para abrir os canais disponíveis.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#809da8;font-size:10px")
        source_layout.addWidget(hint)
        splitter.addWidget(source_frame)

        self.video_host = QWidget()
        self.video_grid = QGridLayout(self.video_host)
        self.video_grid.setContentsMargins(0, 0, 0, 0)
        self.video_grid.setSpacing(5)
        splitter.addWidget(self.video_host)

        inspector = QFrame()
        self.live_inspector = inspector
        inspector.setObjectName("InspectorPane")
        # 0.2.32: the inspector now hosts microphone/talkback controls as well as
        # PTZ. Keep a useful minimum, but allow the operator to resize it instead
        # of clipping long PipeWire device names outside the window.
        inspector.setMinimumWidth(285)
        inspector.setMaximumWidth(460)
        inspector_shell = QVBoxLayout(inspector)
        inspector_shell.setContentsMargins(4, 6, 2, 6)
        inspector_shell.setSpacing(0)
        self.live_inspector_scroll = QScrollArea()
        self.live_inspector_scroll.setObjectName("InspectorScroll")
        self.live_inspector_scroll.setWidgetResizable(True)
        self.live_inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.live_inspector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.live_inspector_scroll.setFrameShape(QFrame.NoFrame)
        self.live_inspector_scroll.setToolTip("Role para acessar os controles sem reduzir o tamanho dos botões")
        inspector_content = QWidget()
        inspector_content.setObjectName("InspectorScrollContent")
        inspector_content.setMinimumWidth(0)
        ins = QVBoxLayout(inspector_content)
        ins.setContentsMargins(6, 4, 6, 6)
        ins.setSpacing(7)
        # Preserve the natural minimum height of the controls. When the Live View is
        # short, the inspector scrolls instead of compressing the PTZ/audio widgets.
        ins.setSizeConstraint(QLayout.SetMinimumSize)
        self.live_inspector_scroll.setWidget(inspector_content)
        inspector_shell.addWidget(self.live_inspector_scroll, 1)

        # Compact selection card: icon + title + one metadata line + state badge.
        # Detailed technical data stays in Diagnostics instead of becoming prose here.
        self.selection_card = QFrame()
        self.selection_card.setObjectName("SelectionCard")
        selection_card_layout = QHBoxLayout(self.selection_card)
        selection_card_layout.setContentsMargins(8, 7, 6, 7)
        selection_card_layout.setSpacing(7)
        self.live_selection_icon = QLabel()
        self.live_selection_icon.setFixedSize(26, 26)
        self.live_selection_icon.setAlignment(Qt.AlignCenter)
        selection_card_layout.addWidget(self.live_selection_icon, 0, Qt.AlignTop)

        selection_text = QVBoxLayout()
        selection_text.setSpacing(2)
        selection_title_row = QHBoxLayout()
        selection_title_row.setSpacing(5)
        self.live_selection_title = QLabel("Nenhuma fonte selecionada")
        self.live_selection_title.setObjectName("SelectionTitle")
        self.live_selection_title.setWordWrap(True)
        selection_title_row.addWidget(self.live_selection_title, 1)
        self.live_selection_status = QLabel("")
        self.live_selection_status.setObjectName("SelectionState")
        self.live_selection_status.hide()
        selection_title_row.addWidget(self.live_selection_status, 0, Qt.AlignTop)
        selection_text.addLayout(selection_title_row)
        self.live_selection_meta = QLabel("Selecione uma câmera ou canal.")
        self.live_selection_meta.setObjectName("SelectionMeta")
        self.live_selection_meta.setWordWrap(True)
        selection_text.addWidget(self.live_selection_meta)
        selection_card_layout.addLayout(selection_text, 1)

        self.inspector_menu_btn = QToolButton()
        self.inspector_menu_btn.setObjectName("ToolbarIconAction")
        self.inspector_menu_btn.setText("⋮")
        self.inspector_menu_btn.setToolTip("Ações da câmera / canal")
        self.inspector_menu_btn.setFixedSize(28, 28)
        self.inspector_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.inspector_menu = QMenu(self.inspector_menu_btn)
        self.rename_channel_action = self.inspector_menu.addAction("Renomear câmera / canal")
        self.rename_channel_action.setEnabled(False)
        self.rename_channel_action.triggered.connect(self.rename_selected_channel)
        self.ask_stream_action = self.inspector_menu.addAction("Perguntar qual stream ao abrir")
        self.ask_stream_action.setCheckable(True)
        self.camera_event_action = self.inspector_menu.addAction("Sonda de eventos IT-Blue (somente leitura)")
        self.camera_event_action.setCheckable(True)
        self.camera_event_action.setEnabled(False)
        self.camera_event_action.triggered.connect(self.toggle_camera_event_probe)
        self.camera_event_diagnostics_action = self.inspector_menu.addAction("Diagnóstico de eventos locais")
        self.camera_event_diagnostics_action.triggered.connect(self.show_camera_event_diagnostics)
        self.inspector_menu_btn.setMenu(self.inspector_menu)
        selection_card_layout.addWidget(self.inspector_menu_btn, 0, Qt.AlignTop)
        ins.addWidget(self.selection_card)
        self.camera_event_status = QLabel("Eventos locais: sonda desligada")
        self.camera_event_status.setWordWrap(True)
        self.camera_event_status.setMinimumWidth(0)
        ins.addWidget(self.camera_event_status)
        self._set_live_selection_summary("Nenhuma fonte selecionada", "Selecione uma câmera ou canal.", "", "SP_ComputerIcon")

        # Stream: one compact row + active badge. Rare actions move to a menu.
        self.stream_section = QFrame()
        self.stream_section.setObjectName("InspectorSection")
        stream_box = QVBoxLayout(self.stream_section)
        stream_box.setContentsMargins(8, 7, 8, 7)
        stream_box.setSpacing(5)
        stream_title_row = QHBoxLayout()
        stream_title_row.setSpacing(5)
        stream_title_row.addWidget(self._standard_icon_label("SP_MediaPlay", "Stream de vídeo", 13))
        self.stream_label = QLabel("STREAM")
        self.stream_label.setObjectName("InspectorSectionTitle")
        stream_title_row.addWidget(self.stream_label)
        stream_title_row.addStretch()
        self.stream_diagnose_btn = QToolButton()
        self.stream_diagnose_btn.setText("Main/Sub")
        self.stream_diagnose_btn.setToolTip("Diagnosticar vídeo, áudio e codecs das rotas cadastradas")
        self.stream_diagnose_btn.setEnabled(False)
        self.stream_diagnose_btn.clicked.connect(self.diagnose_selected_streams)
        stream_title_row.addWidget(self.stream_diagnose_btn)
        stream_box.addLayout(stream_title_row)
        stream_row = QHBoxLayout()
        stream_row.setSpacing(5)
        self.stream_combo = QComboBox()
        self.stream_combo.addItem("Automático", "auto")
        self.stream_combo.addItem("Substream", "sub")
        self.stream_combo.addItem("Main stream", "main")
        self.stream_combo.setEnabled(False)
        self.stream_combo.currentIndexChanged.connect(self.change_selected_channel_stream)
        stream_row.addWidget(self.stream_combo, 1)
        stream_box.addLayout(stream_row)
        self.stream_active_label = QLabel("○ aguardando stream")
        self.stream_active_label.setStyleSheet("color:#809da8;font-size:10px;padding:1px 2px")
        self.stream_active_label.setToolTip("Stream realmente usado pelo decoder, inclusive quando Automático faz fallback")
        stream_box.addWidget(self.stream_active_label)
        # Keep workspace compatibility through the existing checkbox state, but
        # expose the setting only through the compact overflow menu.
        self.ask_stream_check = QCheckBox(self.stream_section)
        self.ask_stream_check.hide()
        self.ask_stream_check.toggled.connect(self.save_live_workspace)
        self.ask_stream_check.toggled.connect(self.ask_stream_action.setChecked)
        self.ask_stream_action.toggled.connect(self.ask_stream_check.setChecked)
        ins.addWidget(self.stream_section)

        # Audio stays available but deliberately compact while field audio is pending.
        self.audio_section = QFrame()
        self.audio_section.setObjectName("InspectorSection")
        audio_box = QVBoxLayout(self.audio_section)
        audio_box.setContentsMargins(8, 7, 8, 7)
        audio_box.setSpacing(5)
        audio_title_row = QHBoxLayout()
        audio_title_row.setSpacing(5)
        audio_title_row.addWidget(self._standard_icon_label("SP_MediaVolume", "Áudio ao vivo", 13))
        audio_title = QLabel("ÁUDIO")
        audio_title.setObjectName("InspectorSectionTitle")
        audio_title_row.addWidget(audio_title)
        self.audio_talkback_badge = QLabel("")
        self.audio_talkback_badge.setStyleSheet(
            "QLabel{color:#85e8b8;background:#153428;border:1px solid #285e49;"
            "border-radius:6px;padding:1px 5px;font-size:8px;font-weight:700;}"
        )
        self.audio_talkback_badge.hide()
        audio_title_row.addWidget(self.audio_talkback_badge)
        audio_title_row.addStretch()
        audio_box.addLayout(audio_title_row)
        self._build_live_audio_controls(audio_box)

        self.audio_capability_label = QLabel("")
        self.audio_capability_label.setWordWrap(True)
        self.audio_capability_label.setStyleSheet("color:#809da8;font-size:9px;padding:3px 1px")
        self.audio_capability_label.hide()
        audio_box.addWidget(self.audio_capability_label)
        self.mic_progress_label = QLabel("")
        self.mic_progress_label.setWordWrap(True)
        self.mic_progress_label.setStyleSheet("color:#9ac5af;font-size:9px;padding:3px 1px")
        self.mic_progress_label.hide()
        audio_box.addWidget(self.mic_progress_label)
        ins.addWidget(self.audio_section)

        # PTZ is contextual: the console appears only for a PTZ-capable/candidate source.
        self.ptz_section = QFrame()
        self.ptz_section.setObjectName("InspectorSection")
        ptz_outer = QVBoxLayout(self.ptz_section)
        ptz_outer.setContentsMargins(8, 7, 8, 7)
        ptz_outer.setSpacing(6)
        ptz_title_row = QHBoxLayout()
        ptz_title_row.setSpacing(5)
        ptz_title_row.addWidget(self._standard_icon_label("SP_ArrowUp", "Controle PTZ / Speed Dome", 13))
        ptz_title = QLabel("PTZ / SPEED DOME")
        ptz_title.setObjectName("InspectorSectionTitle")
        ptz_title_row.addWidget(ptz_title)
        ptz_title_row.addStretch()
        ptz_outer.addLayout(ptz_title_row)
        self.ptz_capability_badge = QLabel("")
        self.ptz_capability_badge.setObjectName("PtzCapabilityBadge")
        self.ptz_capability_badge.hide()
        ptz_title_row.addWidget(self.ptz_capability_badge)

        self.ptz_panel = QFrame()
        self.ptz_panel.setObjectName("PtzPanel")
        ptz_panel_layout = QVBoxLayout(self.ptz_panel)
        ptz_panel_layout.setContentsMargins(9, 9, 9, 9)
        ptz_panel_layout.setSpacing(8)
        move_caption = QLabel("MOVIMENTO")
        move_caption.setObjectName("PtzControlCaption")
        move_caption.setAlignment(Qt.AlignCenter)
        ptz_panel_layout.addWidget(move_caption)
        self.ptz_pad = QWidget()
        ptz_grid = QGridLayout(self.ptz_pad)
        ptz_grid.setContentsMargins(0, 0, 0, 0)
        ptz_grid.setHorizontalSpacing(5)
        ptz_grid.setVerticalSpacing(5)
        self.ptz_buttons = {}
        button_specs = [
            ("up-left", "↖", "Mover para cima e esquerda", 0, 0),
            ("up", "↑", "Mover para cima", 0, 1),
            ("up-right", "↗", "Mover para cima e direita", 0, 2),
            ("left", "←", "Mover para esquerda", 1, 0),
            ("stop", "STOP", "Parar movimento PTZ imediatamente", 1, 1),
            ("right", "→", "Mover para direita", 1, 2),
            ("down-left", "↙", "Mover para baixo e esquerda", 2, 0),
            ("down", "↓", "Mover para baixo", 2, 1),
            ("down-right", "↘", "Mover para baixo e direita", 2, 2),
        ]
        for key, text, tip, row, col in button_specs:
            btn = QToolButton()
            btn.setObjectName("PtzStopButton" if key == "stop" else "PtzPadButton")
            btn.setText(text)
            btn.setFixedSize(52, 46)
            btn.setEnabled(False)
            btn.setToolTip(tip + ("" if key == "stop" else " • pressione e segure"))
            if key == "stop":
                btn.clicked.connect(self.stop_selected_ptz_hold)
            else:
                btn.pressed.connect(lambda d=key: self.start_selected_ptz_hold(d))
                btn.released.connect(self.stop_selected_ptz_hold)
            ptz_grid.addWidget(btn, row, col)
            self.ptz_buttons[key] = btn
        ptz_panel_layout.addWidget(self.ptz_pad, 0, Qt.AlignHCenter)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(7)
        speed_caption = QLabel("VELOCIDADE")
        speed_caption.setObjectName("PtzControlCaption")
        speed_row.addWidget(speed_caption)
        self.ptz_speed_slider = QSlider(Qt.Horizontal)
        self.ptz_speed_slider.setRange(10, 100)
        self.ptz_speed_slider.setValue(45)
        self.ptz_speed_slider.setEnabled(False)
        self.ptz_speed_slider.setToolTip("Velocidade do movimento PTZ • aplicada no próximo movimento")
        speed_row.addWidget(self.ptz_speed_slider, 1)
        self.ptz_speed_value = QLabel("45%")
        self.ptz_speed_value.setObjectName("PtzSpeedValue")
        self.ptz_speed_value.setMinimumWidth(34)
        self.ptz_speed_value.setAlignment(Qt.AlignCenter)
        self.ptz_speed_slider.valueChanged.connect(lambda value: self.ptz_speed_value.setText(f"{value}%"))
        speed_row.addWidget(self.ptz_speed_value)
        ptz_panel_layout.addLayout(speed_row)
        ptz_outer.addWidget(self.ptz_panel)

        self.ptz_status_label = QLabel("")
        self.ptz_status_label.setWordWrap(True)
        self.ptz_status_label.setStyleSheet("color:#809da8;font-size:9px")
        self.ptz_status_label.hide()
        ptz_outer.addWidget(self.ptz_status_label)
        ins.addWidget(self.ptz_section)

        # Diagnostics stays available as a discreet icon. Configuration is already
        # present in the main navigation, so duplicating it here adds visual noise.
        action_row = QHBoxLayout()
        action_row.addStretch()
        self.diag_toggle = QToolButton()
        self.diag_toggle.setObjectName("ToolbarIconAction")
        self.diag_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.diag_toggle.setToolTip("Diagnóstico do Live View")
        self.diag_toggle.setCheckable(True)
        self.diag_toggle.toggled.connect(self.toggle_live_diagnostics)
        action_row.addWidget(self.diag_toggle)
        ins.addLayout(action_row)

        self.live_activity = QLabel("Nenhum evento registrado.")
        self.live_activity.hide()
        ins.addStretch()

        self.stream_section.hide()
        self.audio_section.hide()
        self.ptz_section.hide()
        splitter.addWidget(inspector)
        self.live_splitter = splitter
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        try:
            inspector_width = max(285, min(460, int(self.ui_settings.value("live/inspector_width", 330))))
        except (TypeError, ValueError):
            inspector_width = 330
        splitter.setSizes([250, 900, inspector_width])
        splitter.splitterMoved.connect(self._save_live_splitter_sizes)
        outer.addWidget(splitter, 1)
        inspector.setVisible(self.inspector_toggle.isChecked())

        self.live_diag_panel = QPlainTextEdit()
        self.live_diag_panel.setReadOnly(True)
        self.live_diag_panel.setMaximumBlockCount(400)
        self.live_diag_panel.setPlaceholderText("Diagnóstico técnico sanitizado do FFmpeg/RTSP aparecerá aqui.")
        self.live_diag_panel.setFixedHeight(170)
        self.live_diag_panel.hide()
        outer.addWidget(self.live_diag_panel)

        self.pages.addWidget(page)
        self.rebuild_video_grid(4)

    def _save_live_splitter_sizes(self, *_args):
        """Persist only the inspector width; the mosaic keeps the remaining space."""
        if not hasattr(self, "live_inspector") or not hasattr(self, "ui_settings") or not self.live_inspector.isVisible():
            return
        width = max(285, min(460, int(self.live_inspector.width() or 330)))
        self.ui_settings.setValue("live/inspector_width", width)

    def set_live_inspector_visible(self, visible):
        if not hasattr(self, "live_inspector"):
            return
        if visible and not self._primary_mosaic_fullscreen:
            self.live_inspector.show()
            try:
                width = max(285, min(460, int(self.ui_settings.value("live/inspector_width", 330))))
            except (TypeError, ValueError):
                width = 330
            current = self.live_splitter.sizes()
            self.live_splitter.setSizes([current[0], max(100, current[1] - width), width])
        else:
            self.live_inspector.hide()
        self.ui_settings.setValue("live/inspector_visible", bool(visible))

    def change_video_layout(self):
        count = int(self.layout_combo.currentData())
        self.rebuild_video_grid(count)
        self.save_live_workspace()

    def stop_tile_stream(self, tile: VideoTile):
        tile._stream_generation = getattr(tile, "_stream_generation", 0) + 1
        target = getattr(self, "_ptz_hold_target", None)
        if target and target["source_key"][0] == tile.index:
            self.stop_selected_ptz_hold()
        if self.talkback_tile_index == tile.index:
            self._talkback_resume_audio = False
            self.stop_talkback()
        self.mic_traces.pop(tile.index, None)
        session = self.live_sessions.pop(tile.index, None)
        if session is not None:
            session.stop()
        if self.live_audio_tile_index == tile.index:
            self.stop_live_audio()
        tile.set_loading(False)

    def stop_all_live_streams(self):
        self._talkback_resume_audio = False
        if getattr(self, "_ptz_active_direction", ""):
            self.stop_selected_ptz_hold()
        self.stop_talkback()
        sessions = list(self.live_sessions.values())
        self.live_sessions.clear()
        for session in sessions:
            session.stop()
        self.stop_live_audio()

    def rebuild_video_grid(self, count: int):
        count = int(count or 4)
        # Preserve slot positions when possible; do not compact sources unexpectedly.
        existing_by_index = {tile.index: dict(tile.source) for tile in self.video_tiles if tile.source}
        overflow = [idx for idx in existing_by_index if idx >= count]
        self.stop_all_live_streams()
        if self._focus_return_state is not None:
            self._focus_return_state = None
            self._restore_video_grid_geometry()
        while self.video_grid.count():
            item = self.video_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        # QGridLayout keeps row/column stretch values even after widgets are removed.
        # Reset the old geometry so 16 -> 4 (and similar) fills the whole viewport.
        for idx in range(20):
            self.video_grid.setRowStretch(idx, 0)
            self.video_grid.setColumnStretch(idx, 0)
            self.video_grid.setRowMinimumHeight(idx, 0)
            self.video_grid.setColumnMinimumWidth(idx, 0)
        self.video_tiles = []
        self.selected_video_tile = None

        columns = int(ceil(sqrt(count)))
        rows = int(ceil(count / columns))
        for i in range(count):
            tile = VideoTile(i)
            tile.set_dense_mode(count)
            tile.activated.connect(self.select_video_tile)
            tile.doubleActivated.connect(self.focus_video_tile)
            tile.closeRequested.connect(self.close_tile_source)
            tile.audioRequested.connect(self.toggle_tile_audio)
            tile.talkRequested.connect(self.show_talkback_info)
            tile.moveRequested.connect(self.move_tile_source)
            tile.setContextMenuPolicy(Qt.CustomContextMenu)
            tile.customContextMenuRequested.connect(lambda pos, t=tile: self.show_tile_context_menu(t, pos))
            r, c = divmod(i, columns)
            self.video_grid.addWidget(tile, r, c)
            self.video_tiles.append(tile)
        for r in range(rows):
            self.video_grid.setRowStretch(r, 1)
        for c in range(columns):
            self.video_grid.setColumnStretch(c, 1)

        if self.video_tiles:
            self.select_video_tile(self.video_tiles[0])
        for idx, source in existing_by_index.items():
            if idx < len(self.video_tiles):
                self.apply_source_to_tile(self.video_tiles[idx], source)
        if overflow:
            self.bottom_notice.setText(
                f"{len(overflow)} fonte(s) fora da nova grade foram fechadas"
            )
        self.save_live_workspace()

    def _refresh_live_selection_from_tile(self, tile: VideoTile | None):
        if tile is None or not isinstance(getattr(tile, "source", None), dict):
            self._set_live_selection_summary("Janela vazia", "Selecione uma câmera ou canal.")
            return
        source = tile.source
        if source.get("type") != "channel":
            self._set_live_selection_summary(str(source.get("title") or "Fonte"), "Sem stream de vídeo")
            return
        device = self.db.get_device(int(source.get("device_id", 0)))
        channel = self.db.get_recorder_channel(int(source.get("channel_id", 0)))
        if not device or not channel:
            self._set_live_selection_summary(str(source.get("title") or "Canal"), "Fonte não encontrada")
            return
        display_name = self.db.channel_display_name(channel)
        active = str(source.get("active_stream") or "").upper()
        state = "AO VIVO" if tile.index in self.live_sessions else ("ONLINE" if bool(channel["available"]) else "CANAL")
        meta = f"{device['name']} · Canal {channel['channel_no']:02d}"
        if active in {"MAIN", "SUB"}:
            meta += f" · {active}"
        self._set_live_selection_summary(display_name, meta, state, "SP_MediaPlay")

    def select_video_tile(self, tile: VideoTile):
        if getattr(self, "_ptz_active_direction", ""):
            self.stop_selected_ptz_hold()
        for candidate in self.video_tiles:
            candidate.set_selected(candidate is tile)
        self.selected_video_tile = tile
        self.refresh_camera_event_badges()
        self._refresh_live_selection_from_tile(tile)
        self.refresh_selected_audio_controls()
        self.refresh_selected_ptz_controls()
        self.refresh_stream_indicator_for_selected()
        self.refresh_live_inspector_visibility()
        if hasattr(self, "live_diag_panel") and self.live_diag_panel.isVisible():
            self.refresh_live_diagnostic_panel()

    def refresh_live_inspector_visibility(self):
        tile = self.selected_video_tile
        has_source = bool(tile and isinstance(tile.source, dict) and tile.source.get("type") == "channel")
        if hasattr(self, "stream_section"):
            self.stream_section.setVisible(has_source)
        if not has_source:
            if hasattr(self, "audio_section"):
                self.audio_section.hide()
            if hasattr(self, "ptz_section"):
                self.ptz_section.hide()

    def move_tile_source(self, source_tile: VideoTile, global_pos):
        """Move/swap channels inside the mosaic without restarting their decoders."""
        if source_tile is None or not source_tile.source:
            return
        target = next(
            (t for t in self.video_tiles if t is not source_tile and t.rect().contains(t.mapFromGlobal(global_pos))),
            None,
        )
        if target is None:
            return
        if getattr(self, "_ptz_active_direction", ""):
            self.stop_selected_ptz_hold()
        self._audio_resume_generation = getattr(self, "_audio_resume_generation", 0) + 1
        a, b = source_tile.index, target.index
        if self.talkback_tile_index == a:
            self.talkback_tile_index = b
        elif self.talkback_tile_index == b:
            self.talkback_tile_index = a
        source_tile.swap_content_with(target)
        sa = self.live_sessions.pop(a, None); sb = self.live_sessions.pop(b, None)
        if sa is not None:
            self.live_sessions[b] = sa
        if sb is not None:
            self.live_sessions[a] = sb
        ma = self.mic_traces.pop(a, None); mb = self.mic_traces.pop(b, None)
        if ma is not None:
            self.mic_traces[b] = ma
        if mb is not None:
            self.mic_traces[a] = mb
        da = self.live_diag_lines.pop(a, None); db = self.live_diag_lines.pop(b, None)
        if da is not None:
            self.live_diag_lines[b] = da
        if db is not None:
            self.live_diag_lines[a] = db
        if self.live_audio_tile_index == a:
            self.live_audio_tile_index = b
        elif self.live_audio_tile_index == b:
            self.live_audio_tile_index = a
        for t in self.video_tiles:
            t.set_audio_active(self.live_audio_tile_index == t.index)
        self.select_video_tile(target)
        self.live_activity.setText(f"Canal movido da janela {a + 1} para a janela {b + 1}.")
        self.save_live_workspace()

    def refresh_stream_indicator_for_selected(self):
        if not hasattr(self, "stream_active_label"):
            return
        tile = self.selected_video_tile
        if hasattr(self, "stream_diagnose_btn"):
            self.stream_diagnose_btn.setEnabled(bool(tile and tile.source and tile.source.get("type") == "channel"))
        active = ""
        if tile is not None and isinstance(tile.source, dict):
            active = str(tile.source.get("active_stream") or "").lower()
        names = {"auto": "Automático", "sub": "Substream", "main": "Main stream"}
        for mode, base in names.items():
            idx = self.stream_combo.findData(mode)
            if idx >= 0:
                self.stream_combo.setItemText(idx, ("● " if mode == active else "") + base)
        if active == "main":
            self.stream_active_label.setText("● MAIN em uso")
            self.stream_active_label.setStyleSheet("color:#55d996;font-size:10px;padding:2px 4px;font-weight:700")
        elif active == "sub":
            self.stream_active_label.setText("● SUBSTREAM em uso")
            self.stream_active_label.setStyleSheet("color:#55d996;font-size:10px;padding:2px 4px;font-weight:700")
        else:
            self.stream_active_label.setText("○ aguardando stream")
            self.stream_active_label.setStyleSheet("color:#809da8;font-size:10px;padding:2px 4px")

    def _restore_video_grid_geometry(self):
        count = max(1, len(self.video_tiles))
        columns = int(ceil(sqrt(count)))
        rows = int(ceil(count / columns))
        for idx in range(20):
            self.video_grid.setRowStretch(idx, 0)
            self.video_grid.setColumnStretch(idx, 0)
        for i, candidate in enumerate(self.video_tiles):
            self.video_grid.removeWidget(candidate)
            r, c = divmod(i, columns)
            candidate.set_dense_mode(count)
            self.video_grid.addWidget(candidate, r, c)
            candidate.show()
        for r in range(rows):
            self.video_grid.setRowStretch(r, 1)
        for c in range(columns):
            self.video_grid.setColumnStretch(c, 1)

    def focus_video_tile(self, tile: VideoTile):
        """Toggle one camera inside the current window without restarting streams.

        Older builds rebuilt a one-tile mosaic, stopped every decoder and then
        rebuilt the old mosaic on return.  That caused a visible freeze and a
        fresh RTSP handshake for every camera.  0.2.22 only rearranges/hides
        existing Qt tiles; sessions and their frame queues remain alive.
        """
        if not tile.source:
            return
        if self._focus_return_state is not None:
            state = dict(self._focus_return_state)
            focused_index = int(state.get("tile_index", tile.index))
            self._focus_return_state = None
            self._restore_video_grid_geometry()
            if 0 <= focused_index < len(self.video_tiles):
                self.select_video_tile(self.video_tiles[focused_index])
            return

        self._focus_return_state = {
            "tile_index": int(tile.index),
            "grid_count": len(self.video_tiles),
            "mosaic_was_fullscreen": bool(self._primary_mosaic_fullscreen),
        }
        for candidate in self.video_tiles:
            self.video_grid.removeWidget(candidate)
            if candidate is not tile:
                candidate.hide()
        for idx in range(20):
            self.video_grid.setRowStretch(idx, 0)
            self.video_grid.setColumnStretch(idx, 0)
        tile.set_dense_mode(1)
        tile.show()
        self.video_grid.addWidget(tile, 0, 0, 1, 1)
        self.video_grid.setRowStretch(0, 1)
        self.video_grid.setColumnStretch(0, 1)
        self.select_video_tile(tile)
        # Enlarge inside the existing window. Fullscreen is an explicit mosaic action.

    def _enter_primary_fullscreen(self):
        self._primary_mosaic_fullscreen = True
        self.topbar.hide(); self.bottombar.hide(); self.live_source_frame.hide(); self.live_inspector.hide()
        self.showFullScreen()

    def _exit_primary_fullscreen(self):
        self._primary_mosaic_fullscreen = False
        self.showNormal()
        self.topbar.show(); self.bottombar.show(); self.live_source_frame.show()
        self.live_inspector.setVisible(self.inspector_toggle.isChecked())

    def toggle_primary_mosaic_fullscreen(self):
        if self._primary_mosaic_fullscreen:
            self._exit_primary_fullscreen()
        else:
            self._enter_primary_fullscreen()

    def new_monitor_window(self):
        if not self.current_site_id:
            return
        self._detached_window_seq += 1
        key = f"monitor-{self._detached_window_seq}"
        while key in self.detached_windows:
            self._detached_window_seq += 1; key = f"monitor-{self._detached_window_seq}"
        win = DetachedMonitorWindow(self, key)
        win.closed.connect(self._detached_closed)
        self.detached_windows[key] = win
        win.show()

    def _detached_closed(self, key: str):
        self.detached_windows.pop(str(key), None)

    def restore_detached_windows(self):
        if not self.current_site_id:
            return
        for state in self.db.list_live_windows(self.current_site_id):
            key = str(state.get("window_key") or "")
            if not key or key in self.detached_windows:
                continue
            try:
                suffix = int(key.rsplit("-", 1)[-1]); self._detached_window_seq = max(self._detached_window_seq, suffix)
            except Exception:
                pass
            win = DetachedMonitorWindow(self, key, state)
            win.closed.connect(self._detached_closed)
            self.detached_windows[key] = win
            win.show()

    def clear_video_grid_sources(self):
        self.stop_all_live_streams()
        for tile in self.video_tiles:
            tile.clear_source()
        if self._focus_return_state is not None:
            self._focus_return_state = None
            self._restore_video_grid_geometry()
        self.save_live_workspace()

    def refresh_source_tree(self, sites, devices):
        expanded_devices = self._expanded_source_device_ids()
        if not self.source_filter.text().strip():
            for i in range(self.source_tree.topLevelItemCount()):
                site_item = self.source_tree.topLevelItem(i)
                for j in range(site_item.childCount()):
                    device_item = site_item.child(j)
                    data = device_item.data(0, Qt.UserRole)
                    if data and data[0] == "device":
                        if device_item.isExpanded():
                            expanded_devices.add(int(data[1]))
                        else:
                            expanded_devices.discard(int(data[1]))
        self.ui_settings.setValue("live/expanded_devices", json.dumps(sorted(expanded_devices)))
        self.source_tree.blockSignals(True)
        self.source_tree.clear()
        site_map = {}
        site_states = {}
        for site in sites:
            item = QTreeWidgetItem([site["name"]])
            item.setData(0, Qt.UserRole, ("site", site["id"]))
            item.setToolTip(0, "Site de monitoramento")
            self.source_tree.addTopLevelItem(item)
            site_map[site["id"]] = item
            site_states[site["id"]] = []

        for device in devices:
            parent = site_map.get(device["site_id"])
            if parent is None:
                continue
            from .device_intelligence import device_tree_label
            label = device_tree_label(device)
            device_item = QTreeWidgetItem([label])
            from .brand_tree import decorate_device_item
            decorate_device_item(device_item,device)
            device_item.setData(0, Qt.UserRole, ("device", device["id"]))
            state = str(device["status"] or "unknown").lower()
            device_item.setIcon(0, status_dot_icon(state))
            identity = resolve_operational_identity(device)
            endpoints = self.db.list_device_endpoints(int(device["id"]))
            endpoint_lines = []
            for ep in endpoints:
                roles = []
                if ep["web_url"]:
                    roles.append("Web")
                if ep["rtsp_url"]:
                    roles.append("RTSP")
                if ep["onvif_url"]:
                    roles.append("ONVIF")
                role_text = "/".join(roles) if roles else "rede"
                marker = "principal" if ep["is_primary"] else "endpoint"
                endpoint_lines.append(f"{ep['ip']} ({marker}; {role_text}; {status_label(ep['status'])})")
            endpoint_text = "\n".join(endpoint_lines) or str(device["ip"])
            device_item.setToolTip(
                0,
                f"{identity.kind_label} • {status_label(state)} • {identity.source}\n"
                f"MAC: {device['mac'] or 'não confirmado'}\n{endpoint_text}",
            )
            parent.addChild(device_item)
            device_item.setExpanded(int(device["id"]) in expanded_devices)
            site_states.setdefault(device["site_id"], []).append(state)

            # Always show the recorder inventory. Availability is a status of a
            # known channel, not a reason to remove that channel from navigation.
            channels = self.db.list_recorder_channels(device["id"])
            for ch in channels:
                ch_name = self.db.channel_display_name(ch)
                child = QTreeWidgetItem([ch_name])
                child.setIcon(0, status_dot_icon("channel" if ch["available"] else "unknown", 7))
                child.setData(0, Qt.UserRole, ("channel", device["id"], ch["id"]))
                source_name = ch["source_name"] or ch["name"] or f"Canal {ch['channel_no']:02d}"
                child.setToolTip(
                    0,
                    f"{source_name} • Canal {ch['channel_no']:02d} • "
                    f"stream={ch['preferred_stream']} • {'disponível' if ch['available'] else 'não confirmado'}",
                )
                device_item.addChild(child)

        for site_id, item in site_map.items():
            states = site_states.get(site_id, [])
            if any(state == "online" for state in states):
                site_state = "online"
            elif states and all(state == "offline" for state in states):
                site_state = "offline"
            else:
                site_state = "unknown"
            item.setIcon(0, status_dot_icon(site_state, 8))
            online = sum(state == "online" for state in states)
            offline = sum(state == "offline" for state in states)
            item.setToolTip(0, f"{online} online • {offline} offline • {len(states)} equipamento(s)")

        for item in site_map.values():
            item.setExpanded(True)
        self.source_tree.blockSignals(False)
        self.filter_source_tree(self.source_filter.text())

    def _expanded_source_device_ids(self):
        try:
            ids = json.loads(str(self.ui_settings.value("live/expanded_devices", "[]")))
            return {int(value) for value in ids} if isinstance(ids, list) else set()
        except (ValueError, TypeError):
            return set()

    def _source_expansion_changed(self, item):
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "device" or self.source_filter.text().strip():
            return
        expanded = self._expanded_source_device_ids()
        device_id = int(data[1])
        if item.isExpanded():
            expanded.add(device_id)
        else:
            expanded.discard(device_id)
        self.ui_settings.setValue("live/expanded_devices", json.dumps(sorted(expanded)))

    def filter_source_tree(self, text: str):
        needle = (text or "").strip().casefold()
        self.source_tree.blockSignals(True)
        expanded = self._expanded_source_device_ids()
        for i in range(self.source_tree.topLevelItemCount()):
            site = self.source_tree.topLevelItem(i)
            site_visible = False
            for j in range(site.childCount()):
                device = site.child(j)
                device_match = needle in device.text(0).casefold()
                child_visible = False
                for k in range(device.childCount()):
                    channel = device.child(k)
                    match = not needle or needle in channel.text(0).casefold() or device_match
                    channel.setHidden(not match)
                    child_visible = child_visible or match
                visible = not needle or device_match or child_visible
                device.setHidden(not visible)
                device.setExpanded(bool(needle and visible) or int(device.data(0, Qt.UserRole)[1]) in expanded)
                site_visible = site_visible or visible
            site.setHidden(bool(needle) and not site_visible and needle not in site.text(0).casefold())
            if needle and not site.isHidden():
                site.setExpanded(True)
        self.source_tree.blockSignals(False)

    def source_selection_changed(self):
        item = self.source_tree.currentItem()
        self.selected_channel_context = None
        self.rename_channel_action.setEnabled(False)
        self.stream_combo.setEnabled(False)
        if item is None:
            self._set_live_selection_summary("Nenhuma fonte selecionada", "Selecione uma câmera ou canal.")
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "device":
            device = self.db.get_device(int(data[1]))
            if device:
                model = clean_model(device["manufacturer"], device["model"] or device["detected_model"])
                credential = "salva no cofre" if device["credential_saved"] else "somente sessão / não salva"
                operational = resolve_operational_identity(device)
                identity = " ".join(part for part in (device["manufacturer"] or "", model if model != "—" else "") if part)
                meta = f"{operational.kind_label} · {device['ip']}"
                if identity and identity.casefold() != str(device['name']).casefold():
                    meta += f" · {identity}"
                self._set_live_selection_summary(
                    device_visual_name(device), meta, str(device["status"] or ""), "SP_ComputerIcon"
                )
        elif data[0] == "channel":
            device_id, channel_id = int(data[1]), int(data[2])
            device = self.db.get_device(device_id)
            channel = self.db.get_recorder_channel(channel_id)
            if device and channel:
                self.selected_channel_context = (device_id, channel_id)
                display_name = self.db.channel_display_name(channel)
                source_name = channel["source_name"] or channel["name"] or f"Canal {channel['channel_no']:02d}"
                self._set_live_selection_summary(
                    display_name,
                    f"{device['name']} · Canal {channel['channel_no']:02d}",
                    "online" if bool(channel["available"]) else "canal",
                    "SP_MediaPlay",
                )
                self.rename_channel_action.setEnabled(True)
                self._stream_combo_sync = True
                idx = self.stream_combo.findData(channel["preferred_stream"] or "auto")
                self.stream_combo.setCurrentIndex(max(0, idx))
                self._stream_combo_sync = False
                self.stream_combo.setEnabled(True)

    def _tile_sources_snapshot(self):
        return [tile.source for tile in self.video_tiles]

    def _select_next_empty_tile(self, after_index: int):
        idx = next_empty_slot(self._tile_sources_snapshot(), after_index)
        if idx is not None and 0 <= idx < len(self.video_tiles):
            self.select_video_tile(self.video_tiles[idx])
            return self.video_tiles[idx]
        return None

    def _ensure_grid_capacity(self, required_slots: int):
        target = smallest_grid_for(required_slots)
        if target <= len(self.video_tiles):
            return
        idx = self.layout_combo.findData(target)
        if idx >= 0:
            self.layout_combo.blockSignals(True)
            self.layout_combo.setCurrentIndex(idx)
            self.layout_combo.blockSignals(False)
        self.rebuild_video_grid(target)

    def _open_channel_in_selected_and_advance(self, device_id: int, channel_id: int, mode: str | None = None):
        existing = next((tile for tile in self.video_tiles if tile.source
                         and tile.source.get("type") == "channel"
                         and int(tile.source.get("device_id") or 0) == int(device_id)
                         and int(tile.source.get("channel_id") or 0) == int(channel_id)), None)
        if existing is not None and mode is None:
            self.select_video_tile(existing)
            return
        if self.selected_video_tile is None and self.video_tiles:
            self.select_video_tile(self.video_tiles[0])
        if self.selected_video_tile is None:
            return
        tile = self.selected_video_tile
        channel = self.db.get_recorder_channel(channel_id)
        if not channel:
            return
        if mode in {"auto", "sub", "main"}:
            self.db.update_channel_preferred_stream(channel_id, mode)
        source = {
            "type": "channel",
            "device_id": int(device_id),
            "channel_id": int(channel_id),
            "title": self.db.channel_display_name(channel),
        }
        if mode in {"sub", "main"}:
            source["forced_stream"] = mode
        self.apply_source_to_tile(tile, source)
        self.save_live_workspace()
        self._select_next_empty_tile(tile.index)

    def source_single_clicked(self, item, _column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "channel":
            device_id, channel_id = int(data[1]), int(data[2])
            if hasattr(self, "ask_stream_check") and self.ask_stream_check.isChecked():
                # The context menu exposes Auto/Sub/Main without a blocking dialog.
                rect = self.source_tree.visualItemRect(item)
                self.show_source_context_menu(rect.center())
                return
            self._open_channel_in_selected_and_advance(device_id, channel_id, None)
        elif data[0] == "device":
            self.open_all_device_channels(int(data[1]))

    def source_double_clicked(self, item, _column):
        # Single-click is the operational VMS action in 0.2.3. Keep the double
        # click handler intentionally inert to avoid opening a source twice.
        return

    def open_all_device_channels(self, device_id: int):
        device = self.db.get_device(int(device_id))
        if not device:
            return
        all_channels = self.db.list_recorder_channels(int(device_id))
        identity = resolve_operational_identity(device)
        channels = channels_for_live_view(all_channels, identity.kind)
        channels += [ch for ch in all_channels if ch not in channels and not bool(ch["available"]) and recoverable_native_channel(device, ch)]
        if not channels:
            if all_channels and identity.kind == "nvr":
                QMessageBox.information(self, "Vídeo pendente",
                    "O NVR informou posições de canais, mas nenhum stream entregou vídeo confirmado.\n\n"
                    "Abra Configuração → Equipamentos → Canais / Stream e veja a coluna Evidência. "
                    "Confira primeiro um canal que mostra imagem no gravador.")
            return
        # Avoid duplicates when the recorder is clicked again: close only its
        # existing tiles and keep cameras from other devices intact.
        for tile in list(self.video_tiles):
            if tile.source and int(tile.source.get("device_id", -1)) == int(device_id):
                self.close_tile_source(tile)
        occupied = sum(1 for tile in self.video_tiles if tile.source)
        required = max(len(channels), occupied + len(channels))
        self._ensure_grid_capacity(required)
        empty_indexes = [tile.index for tile in self.video_tiles if not tile.source]
        if len(empty_indexes) < len(channels):
            # A full/small workspace should not silently overwrite arbitrary tiles.
            # Open the recorder as a clean workspace instead.
            self.clear_video_grid_sources()
            empty_indexes = [tile.index for tile in self.video_tiles]
        opened = 0
        last_idx = -1
        for ch, idx in zip(channels, empty_indexes):
            source = {
                "type": "channel",
                "device_id": int(device_id),
                "channel_id": int(ch["id"]),
                "title": self.db.channel_display_name(ch),
            }
            self.apply_source_to_tile(self.video_tiles[idx], source)
            opened += 1
            last_idx = idx
        self.save_live_workspace()
        next_idx = next_empty_slot(self._tile_sources_snapshot(), last_idx)
        if next_idx is not None:
            self.select_video_tile(self.video_tiles[next_idx])
        elif self.video_tiles:
            self.select_video_tile(self.video_tiles[0])
        suffix = "" if opened == len(channels) else f" • {len(channels) - opened} não couberam nesta página"
        self.bottom_notice.setText(
            f"{opened} canal(is) de {device['name']} abertos no mosaico{suffix}"
        )

    def _credentials_for_device(self, device_id: int):
        if device_id in self.session_credentials:
            return self.session_credentials[device_id]
        device = self.db.get_device(device_id)
        if not device or not device["credential_saved"]:
            return None
        password = self.credential_store.get_password(device_id)
        if password is None:
            return None
        username = device["credential_username"] or "admin"
        self.session_credentials[device_id] = (username, password)
        return username, password

    def _stream_choice(self, channel, forced: str | None = None):
        from .hik_sdk import live_choice
        choice=live_choice(self.db.get_device(channel["device_id"]),channel["channel_no"],forced or channel["preferred_stream"]) if getattr(self,"db",None) is not None else None
        if choice is not None:return choice
        pref = forced or channel["preferred_stream"] or "auto"
        main_url = channel["main_rtsp_url"] or channel["rtsp_url"]
        sub_url = channel["sub_rtsp_url"] or ""
        if pref == "main":
            return ("main", main_url, "", "") if main_url else ("sub", sub_url, "", "")
        if pref == "sub":
            return ("sub", sub_url, "", "") if sub_url else ("main", main_url, "", "")
        # Recorder-backed IP/proxy channels (for example MHDX channel 5) first
        # retry the profile that actually delivered the last frame. This cache
        # does not override operator-forced Main/Sub and is deliberately not used
        # for legacy analogue channels.
        keys = set(channel.keys()) if hasattr(channel, "keys") else set()
        route_kind = str(channel["route_kind"] or "") if "route_kind" in keys else "via_recorder"
        channel_kind = str(channel["channel_kind"] or "") if "channel_kind" in keys else "unknown"
        last_good = str(channel["last_good_stream"] or "") if "last_good_stream" in keys else ""
        if route_kind == "via_recorder" and channel_kind == "ip" and last_good in {"main", "sub"}:
            primary_url = main_url if last_good == "main" else sub_url
            fallback_kind = "sub" if last_good == "main" else "main"
            fallback_url = sub_url if last_good == "main" else main_url
            if primary_url:
                return last_good, primary_url, fallback_kind if fallback_url else "", fallback_url
        # Auto follows the VMS convention: lighter substream in mosaics and
        # main stream in single view, but keeps a transparent fallback.
        if len(self.video_tiles) == 1:
            primary_kind, primary_url = "main", main_url
            fallback_kind, fallback_url = "sub", sub_url
        else:
            primary_kind, primary_url = "sub", sub_url
            fallback_kind, fallback_url = "main", main_url
        if not primary_url:
            primary_kind, primary_url, fallback_kind, fallback_url = fallback_kind, fallback_url, "", ""
        return primary_kind, primary_url, fallback_kind, fallback_url

    def _live_target_fps(self) -> int:
        """Balance mosaic smoothness against GUI/decoder load.

        Field testing showed that running every tile at 10 fps creates avoidable
        CPU and Qt scaling pressure in 9/16-camera mosaics.  A single/four view
        stays fluid while larger grids use a VMS-style lower preview cadence.
        """
        count = max(1, len(self.video_tiles))
        if count <= 4:
            return 10
        if count <= 9:
            return 8
        if count <= 16:
            return 6
        if count <= 36:
            return 5
        if count <= 64:
            return 4
        return 3

    def apply_source_to_tile(self, tile: VideoTile, source: dict):
        if getattr(self, "_closing_app", False) or tile not in self.video_tiles:
            return
        self.stop_tile_stream(tile)
        if source.get("type") != "channel":
            tile.set_source(source.get("title", "Fonte"), "Fonte sem stream de vídeo", "Somente leitura", source)
            return
        device = self.db.get_device(int(source["device_id"]))
        channel = self.db.get_recorder_channel(int(source["channel_id"]))
        if not device or not channel:
            tile.set_source("Canal", "Fonte não encontrada", "Atualize a árvore", source)
            return
        display_name = self.db.channel_display_name(channel)
        route_kind = channel["route_kind"] if "route_kind" in channel.keys() else "via_recorder"
        if not bool(channel["available"]) and not recoverable_native_channel(device, channel) and (route_kind == "direct" or resolve_operational_identity(device).kind == "nvr"):
            tile.set_source(display_name, "Vídeo ainda não confirmado", "Use Configuração → Equipamentos → Canais / Stream para consultar a evidência", source)
            return
        forced_stream = source.get("forced_stream")
        stream_kind, url, fallback_kind, fallback_url = self._stream_choice(channel, forced_stream)
        source = dict(source)
        source.update({"title": display_name, "active_stream": stream_kind, "fallback_stream": fallback_kind,"manufacturer":device["manufacturer"]})
        footer_name = "Main stream" if stream_kind == "main" else "Substream"
        transport_label = ("Cloud via Wine" if str(url or "").lower().startswith("intelbras-wine://") else "Cloud via ponte" if str(url or "").lower().startswith("intelbras-cloud://")
                           else "Hikvision SDK local" if str(url or "").lower().startswith("hik-sdk://") else "DVRIP" if str(url or "").lower().startswith("dvrip://") else "RTSP")
        route_label = "Direta" if route_kind == "direct" else f"Via {device['name']}"
        tile.set_source(display_name, f"{route_label}\nConectando ao {footer_name}…", f"{footer_name} • {transport_label} • somente leitura", source)
        if tile is self.selected_video_tile:
            self._refresh_live_selection_from_tile(tile)
        audio_info = channel_audio_info(device, channel)
        if str(url).startswith("hik-sdk:"):audio_info={"can_listen":False,"can_talk":False,"label":"Áudio SDK em validação"}
        talk_reason = str(audio_info.get("talkback_netsdk_runtime") or "") if audio_info.get("talkback_pending") else ""
        if audio_info.get("talkback_pending") and not talk_reason:
            talk_reason = "MIC indisponível neste canal • transporte de retorno ainda não homologado"
        tile.set_audio_capabilities(
            bool(audio_info["can_listen"] or audio_info.get("can_probe_listen")), audio_info["can_talk"],
            active=(self.live_audio_tile_index == tile.index), label=audio_info["label"],
            talk_pending=bool(audio_info.get("talkback_pending")), talk_reason=talk_reason,
        )
        if tile is self.selected_video_tile:
            self.refresh_selected_audio_controls()
        if not url:
            tile.body.setText("Stream indisponível para este perfil")
            return
        credentials = self._credentials_for_device(device["id"])
        if not credentials:
            tile.body.setText(
                "Credencial necessária para o vídeo.\n"
                "Abra Configuração → Equipamentos → Ler canais do gravador\n"
                "e marque ‘Salvar credencial com segurança’."
            )
            tile.footer.setText(f"{footer_name} • aguardando credencial")
            return
        username, password = credentials
        session = create_live_stream_session(
            url, username, password, fps=self._live_target_fps(),
            profile_name=("Main stream" if stream_kind == "main" else "Substream"),
            fallback_url=fallback_url,
            fallback_name=("Main stream" if fallback_kind == "main" else "Substream") if fallback_kind else "",
            stop_after_initial_failures=3 if route_kind == "direct" else 0,
            transport_fallback=(route_kind == "direct" and not str(url or "").lower().startswith("dvrip://")),
        )
        if uses_hikvision_recordings(device) and stream_kind=='main':
            session.frame_width=1280;session.frame_height=720
        self.live_sessions[tile.index] = session
        session.start()
        tile.set_loading(True)

    def update_performance_indicator(self):
        sessions = list(self.live_sessions.values())
        for window in self.detached_windows.values():
            sessions.extend(window.sessions.values())
        pids = [os.getpid()]
        for session in sessions:
            process = getattr(session, "_process", None)
            if process is not None and process.poll() is None:
                pids.append(process.pid)
        from .pc_capacity_ui import monitor_for
        monitor = monitor_for(self)
        if monitor.tick(sessions):
            self.statusBar().showMessage("Desempenho sob pressão ou quadros reduzidos acima da estimativa. Considere Substream/reduzir câmeras; confira também a origem/rede.", 15000)
        sample = process_sample(pids)
        cpu = cpu_percent(self._performance_previous, sample)
        self._performance_previous = sample
        cpu_text = f"{cpu}%" if cpu is not None else "—"
        self.performance_label.setText(f"Streams: {len(sessions)} • CPU: {cpu_text} • RAM: {sample[2]:.0f} MiB")
        if cpu is not None:
            self.performance_samples.append((len(self.video_tiles), len(sessions), cpu, sample[2]))
            del self.performance_samples[:-120]

    def show_performance_comparison(self):
        rows = []
        for grid in (4, 9, 16):
            samples = [row for row in self.performance_samples if row[0] == grid]
            if not samples:
                rows.append(f"{grid} câmeras: ainda sem medição nesta sessão")
                continue
            recent = samples[-10:]
            mean = lambda index: sum(row[index] for row in recent) / len(recent)
            rows.append(
                f"{grid} câmeras: {len(recent)} amostra(s) • streams {mean(1):.1f} "
                f"• CPU {mean(2):.0f}% • RAM {mean(3):.0f} MiB"
            )
        QMessageBox.information(self, "Desempenho do monitoramento", "\n".join(rows)
            + "\n\nMédias recentes desta sessão, incluindo Sentinel e FFmpeg do vídeo. "
              "CPU pode passar de 100% em computadores com vários núcleos.")

    def poll_live_streams(self):
        if getattr(self, "_closing_app", False):
            return
        self.poll_camera_events()
        for tile in list(self.video_tiles):
            session = self.live_sessions.get(tile.index)
            tile.sync_loading(session)
            if session is None:
                continue
            status = session.latest_status()
            if status:
                active = session.active_profile
                tile.footer.setText(f"{status} • {active}")
                active_kind = "main" if active.lower().startswith("main") else "sub"
                if tile.source:
                    tile.source["active_stream"] = active_kind
                tile.set_stream_indicator(active_kind)
                if tile is self.selected_video_tile:
                    self.refresh_stream_indicator_for_selected()
                    self._refresh_live_selection_from_tile(tile)
                pix = tile.body.pixmap()
                stream_failed = status.startswith(("Sem vídeo", "Host temporariamente inacessível"))
                terminal_failure = getattr(session, "current_state", "") in {"unavailable", "authentication"}
                if stream_failed or terminal_failure or getattr(session, "last_error_class", "") in {"frame_timeout", "truncated_frame"}:
                    # Do not leave the last decoded image looking live while this
                    # tile's own worker is recovering its RTSP/decoder session.
                    tile.body.setPixmap(QPixmap())
                    tile.body.setText(
                        status if stream_failed or terminal_failure else "Sem frames • recuperando este canal…"
                    )
                elif "AO VIVO" not in status and (pix is None or pix.isNull()):
                    tile.body.setText(status)
            for line in session.drain_diagnostics():
                self.append_live_diagnostic(tile, line)
            snapshot_fn = getattr(session, "diagnostics_snapshot", None)
            if callable(snapshot_fn):
                snapshot = snapshot_fn()
                cause = str(snapshot.get("last_reconnect_cause") or "")
                if cause and cause != getattr(session, "_reported_reconnect_cause", ""):
                    session._reported_reconnect_cause = cause
                    last_frame = snapshot.get("last_frame_seconds_ago")
                    frame_age = f"{last_frame:g}s" if isinstance(last_frame, (int, float)) else "nunca"
                    errors = ", ".join(snapshot.get("recent_errors") or ()) or "nenhum classificado"
                    self.append_live_diagnostic(
                        tile,
                        f"Live View • perfil {snapshot.get('profile') or '?'} • alvo {snapshot.get('fps_target') or '?'} FPS "
                        f"• aberto {snapshot.get('opened_seconds') or 0:g}s • último frame {frame_age} "
                        f"• FFmpeg {'ativo' if snapshot.get('process_alive') else 'encerrado'} "
                        f"• erro(s): {errors} • recuperação: {cause}",
                    )
            frame = session.latest_frame()
            if frame is not None:
                image = QImage(
                    frame.pixels, frame.width, frame.height, frame.width * 3, QImage.Format_RGB888
                ).copy()
                tile.set_frame(image)
                tile.update_media_badge(session)
                # Persist the last profile that actually produced a frame. The
                # auto chooser uses this only for recorder-backed IP/proxy
                # channels, so legacy analogue behaviour is not changed.
                if tile.source and isinstance(session, (DvripLiveStreamSession, IntelbrasCloudLiveSession)) and not getattr(session, "_inventory_frame_confirmed", False):
                    try:
                        session._inventory_frame_confirmed = self.db.confirm_native_channel_frame(int(tile.source.get("channel_id", 0)), route=getattr(session,"active_url",session.url))
                    except Exception:
                        pass
                if tile.source and not tile.source.get("_last_good_saved"):
                    active_kind = "main" if session.active_profile.lower().startswith("main") else "sub"
                    try:
                        self.db.update_channel_last_good_stream(int(tile.source.get("channel_id", 0)), active_kind)
                        tile.source["_last_good_saved"] = active_kind
                    except Exception:
                        pass
        audio = self.live_audio_session
        if audio is not None and self.live_audio_tile_index is not None:
            idx = self.live_audio_tile_index
            tile = self.video_tiles[idx] if 0 <= idx < len(self.video_tiles) else None
            audio_diag_changed = False
            status = audio.latest_status()
            if status and tile is not None:
                audio_diag_changed = True
                self.audio_capability_label.setText(status)
                self.append_live_diagnostic(tile, f"[{datetime.now().strftime('%H:%M:%S')}] {status}")
                if status.startswith("🔊 Áudio ativo"):
                    self._set_live_audio_bar("active")
                elif status.startswith("Falha") or status.startswith("Sem faixa") or "indisponível" in status.lower():
                    self._set_live_audio_bar("failure", "falha")
                else:
                    clean = status.replace("Áudio:", "").replace("…", "").strip()
                    self._set_live_audio_bar("connecting", clean[:42] if clean else "conectando")
            for line in audio.drain_diagnostics():
                if tile is not None:
                    audio_diag_changed = True
                    self.append_live_diagnostic(tile, f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
            if (
                audio_diag_changed and tile is self.selected_video_tile
                and hasattr(self, "live_diag_panel") and self.live_diag_panel.isVisible()
            ):
                self.refresh_live_diagnostic_panel()
            # If an on-demand probe discovered an audio track, remember it so
            # subsequent clicks take the fast path (notably MHDX IP/proxy ch. 5).
            if tile is not None and audio.detected_codec and tile.source:
                try:
                    channel_id = int(tile.source.get("channel_id", 0))
                    current = self.db.get_recorder_channel(channel_id)
                    if current and (str(current["audio_codec"] or "") != str(audio.detected_codec) or str(current["audio_mode"] or "") != "listen"):
                        self.db.update_channel_audio(
                            channel_id, "listen", str(audio.detected_codec), int(audio.detected_sample_rate or 0),
                            int(current["audio_channels"] or 0), "Áudio validado no Live View via rota RTSP ativa",
                        )
                except Exception:
                    pass
            if audio.finished:
                if tile is not None:
                    tile.set_audio_active(False)
                failed_identity = self.live_audio_identity
                self.live_audio_session = None
                self.live_audio_tile_index = None
                if failed_identity:
                    self._set_live_audio_bar("failure", "interrompido")
                    self.live_audio_identity = ""
                    QTimer.singleShot(2500, lambda generation=getattr(self, "_audio_resume_generation", 0):
                                      self._reset_audio_bar_if_idle(generation))
                self.refresh_selected_audio_controls()

        talk = self.talkback_session
        if talk is not None:
            idx = self.talkback_tile_index
            talk_tile = self.video_tiles[idx] if idx is not None and 0 <= idx < len(self.video_tiles) else None
            status = talk.latest_status()
            if status:
                self._update_mic_trace(idx, status)
                self.audio_capability_label.setText(status)
                self.audio_capability_label.show()
                if talk_tile is not None:
                    self.append_live_diagnostic(talk_tile, f"[{datetime.now().strftime('%H:%M:%S')}] {status}")
            for line in talk.drain_diagnostics():
                self._update_mic_trace(idx, line)
                if talk_tile is not None:
                    self.append_live_diagnostic(talk_tile, f"[{datetime.now().strftime('%H:%M:%S')}] PTT • {line}")
            if talk.finished:
                self.talkback_session = None
                old_idx = self.talkback_tile_index
                self.talkback_tile_index = None
                if self._talkback_resume_audio and old_idx is not None and 0 <= old_idx < len(self.video_tiles):
                    self._talkback_resume_audio = False
                    resume_delay = max(180, int(getattr(talk, "resume_delay_ms", 180) or 180))
                    tile = self.video_tiles[old_idx]
                    generation = getattr(tile, "_stream_generation", 0)
                    audio_generation = getattr(self, "_audio_resume_generation", 0)
                    source = dict(tile.source or {})
                    QTimer.singleShot(resume_delay, lambda: self._resume_audio_after_talkback(
                        tile, source, generation, audio_generation))
                else:
                    self._talkback_resume_audio = False
                self.refresh_selected_audio_controls()

    def _update_mic_trace(self, tile_index, line: str):
        if tile_index is None:
            return
        trace = self.mic_traces.setdefault(tile_index, MicTrace())
        summary = trace.observe(line)
        if self.selected_video_tile is not None and self.selected_video_tile.index == tile_index:
            self.mic_progress_label.setText(summary)
            self.mic_progress_label.show()

    def _audio_context_for_tile(self, tile: VideoTile):
        if tile is None or not tile.source or tile.source.get("type") != "channel":
            return None
        device = self.db.get_device(int(tile.source.get("device_id", 0)))
        channel = self.db.get_recorder_channel(int(tile.source.get("channel_id", 0)))
        if not device or not channel:
            return None
        info = channel_audio_info(device, channel)
        active = tile.source.get("active_stream") or "sub"
        urls = ordered_audio_urls(
            channel["main_rtsp_url"] or "",
            channel["sub_rtsp_url"] or "",
            channel["rtsp_url"] or "",
            active,
        )
        return device, channel, info, urls

    def refresh_microphone_inputs_async(self, force: bool = False):
        if getattr(self, "_closing_app", False):
            return
        future = self.microphone_scan_future
        if future is not None and not future.done():
            return
        if force:
            ffmpeg_microphone_inputs.cache_clear()
        self.microphone_scan_complete = False
        if hasattr(self, "microphone_combo"):
            self.microphone_combo.blockSignals(True)
            self.microphone_combo.clear()
            self.microphone_combo.addItem("Detectando microfones…", None)
            self.microphone_combo.blockSignals(False)
            self.microphone_refresh_btn.setEnabled(False)
        self.microphone_scan_future = self.audio_executor.submit(discover_microphone_inputs)
        QTimer.singleShot(100, self._poll_microphone_inputs)

    def _poll_microphone_inputs(self):
        if getattr(self, "_closing_app", False):
            return
        future = self.microphone_scan_future
        if future is None:
            return
        if not future.done():
            QTimer.singleShot(100, self._poll_microphone_inputs)
            return
        try:
            self.microphone_inputs = list(future.result() or [])
        except Exception:
            self.microphone_inputs = []
        self.microphone_scan_complete = True
        self.microphone_scan_future = None
        self._populate_microphone_combo()
        if hasattr(self, "microphone_refresh_btn"):
            self.microphone_refresh_btn.setEnabled(True)
        self.refresh_selected_audio_controls()

    def _populate_microphone_combo(self):
        if not hasattr(self, "microphone_combo"):
            return
        combo = self.microphone_combo
        combo.blockSignals(True)
        combo.clear()
        preferred = (self.audio_input_preferences.backend, self.audio_input_preferences.source)
        selected_index = -1
        for index, mic in enumerate(self.microphone_inputs):
            combo.addItem(mic.label, (mic.backend, mic.source))
            if (mic.backend, mic.source) == preferred:
                selected_index = index
        if not self.microphone_inputs:
            combo.addItem("Nenhum microfone compatível", None)
        else:
            if selected_index < 0:
                selected_index = 0
                chosen = self.microphone_inputs[0]
                self.audio_input_preferences.backend = chosen.backend
                self.audio_input_preferences.source = chosen.source
                save_audio_input_preferences(data_dir(), self.audio_input_preferences)
            combo.setCurrentIndex(selected_index)
        combo.blockSignals(False)
        mic = self._selected_microphone_input()
        if mic is not None:
            combo.setToolTip(f"Entrada local usada pelo Push-to-Talk\n{mic.label}\n{mic.source}")
        elif not self.microphone_inputs:
            combo.setToolTip("Nenhum microfone local compatível encontrado")

    def _selected_microphone_input(self) -> MicrophoneInput | None:
        if not self.microphone_inputs:
            return None
        data = self.microphone_combo.currentData() if hasattr(self, "microphone_combo") else None
        if isinstance(data, tuple) and len(data) == 2:
            for mic in self.microphone_inputs:
                if (mic.backend, mic.source) == tuple(data):
                    return mic
        return self.microphone_inputs[0]

    def change_microphone_input(self, _index: int = -1):
        mic = self._selected_microphone_input()
        if mic is None:
            return
        self.audio_input_preferences.backend = mic.backend
        self.audio_input_preferences.source = mic.source
        save_audio_input_preferences(data_dir(), self.audio_input_preferences)
        if hasattr(self, "microphone_combo"):
            self.microphone_combo.setToolTip(f"Entrada local usada pelo Push-to-Talk\n{mic.label}\n{mic.source}")
        self.refresh_selected_audio_controls()

    def change_microphone_gain(self, _index: int = -1):
        if not hasattr(self, "microphone_gain_slider"):
            return
        percent = int(self.microphone_gain_slider.value())
        self.microphone_gain_value.setText(f"{percent}%")
        self.audio_input_preferences.gain_db = microphone_gain_db_for_percent(percent)
        save_audio_input_preferences(data_dir(), self.audio_input_preferences)
        self.refresh_selected_audio_controls()

    def set_microphone_gain_controls_enabled(self, enabled: bool):
        enabled = bool(enabled)
        self.microphone_gain_slider.setEnabled(enabled)
        self.microphone_gain_reset_btn.setEnabled(enabled)

    def change_netsdk_talk_mode(self, _index: int = -1):
        if not hasattr(self, "netsdk_mode_combo"):
            return
        mode = str(self.netsdk_mode_combo.currentData() or "literal-reference")
        self.audio_input_preferences.netsdk_talk_mode = mode
        save_audio_input_preferences(data_dir(), self.audio_input_preferences)
        self.refresh_selected_audio_controls()

    def test_selected_microphone_async(self):
        if getattr(self, "_closing_app", False):
            return
        future = self.microphone_test_future
        if future is not None and not future.done():
            return
        microphone = self._selected_microphone_input()
        if microphone is None:
            self.audio_capability_label.setText("Nenhum microfone local disponível para teste")
            self.audio_capability_label.show()
            return
        if self.talkback_session is not None:
            self.audio_capability_label.setText("Encerre o Push-to-Talk antes de testar o microfone local")
            self.audio_capability_label.show()
            return
        gain = float(self.audio_input_preferences.gain_db)
        self.audio_capability_label.setText(f"Testando {microphone.label} em background…")
        self.audio_capability_label.show()
        if hasattr(self, "microphone_test_btn"):
            self.microphone_test_btn.setEnabled(False)
        self.microphone_test_future = self.audio_executor.submit(
            probe_microphone_level, microphone, gain_db=gain, duration=1.25
        )
        QTimer.singleShot(100, self._poll_microphone_test)

    def _poll_microphone_test(self):
        if getattr(self, "_closing_app", False):
            return
        future = self.microphone_test_future
        if future is None:
            return
        if not future.done():
            QTimer.singleShot(100, self._poll_microphone_test)
            return
        try:
            result = future.result()
        except Exception as exc:
            result = None
            detail = f"{type(exc).__name__}: {exc}"
        else:
            detail = str(getattr(result, "detail", "") or "")
        self.microphone_test_future = None
        self.netsdk_install_future = None
        if hasattr(self, "microphone_test_btn"):
            self.microphone_test_btn.setEnabled(True)
        microphone = self._selected_microphone_input()
        label = microphone.label if microphone else "Microfone"
        if result is not None and bool(getattr(result, "ok", False)):
            mean_db = getattr(result, "mean_db", None)
            peak_db = getattr(result, "peak_db", None)
            mean_text = f"{float(mean_db):.1f} dB" if mean_db is not None else "n/d"
            peak_text = f"{float(peak_db):.1f} dB" if peak_db is not None else "n/d"
            gain = float(self.audio_input_preferences.gain_db)
            self.audio_capability_label.setText(
                f"{label} • médio {mean_text} • pico {peak_text} • MIC {microphone_gain_percent_for_db(gain)}%"
            )
        else:
            self.audio_capability_label.setText(f"Teste do MIC falhou • {detail or 'sem leitura de nível'}")
        self.audio_capability_label.show()

    def refresh_selected_audio_controls(self):
        if not hasattr(self, "listen_audio_btn"):
            return
        tile = self.selected_video_tile
        ctx = self._audio_context_for_tile(tile) if tile else None
        if not ctx:
            self.listen_audio_btn.setEnabled(False)
            self.listen_audio_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
            self.listen_audio_btn.setToolTip("Áudio não confirmado para a seleção")
            self.audio_volume_slider.setEnabled(False)
            talk_running = self.talkback_session is not None
            self.talkback_btn.setEnabled(talk_running)
            self.talkback_btn.setVisible(talk_running)
            self.talkback_btn.setChecked(talk_running)
            self.talkback_btn.setText("PARAR" if talk_running else "MIC")
            self.talkback_btn.setToolTip("Parar a sessão de microfone ativa" if talk_running else "Áudio não confirmado")
            if hasattr(self, "microphone_row"):
                self.microphone_row.hide()
            if hasattr(self, "microphone_test_btn"):
                self.microphone_test_btn.setEnabled(False)
            if hasattr(self, "netsdk_mode_combo"):
                self.netsdk_mode_combo.hide()
                self.netsdk_mode_label.hide()
            if hasattr(self, "audio_talkback_badge"):
                self.audio_talkback_badge.hide()
            self.audio_capability_label.hide()
            self.mic_progress_label.hide()
            if hasattr(self, "audio_section"):
                self.audio_section.setVisible(talk_running)
            return
        _device, _channel, info, _url = ctx
        can_listen = bool(info["can_listen"] or info.get("can_probe_listen"))
        can_talk = bool(info["can_talk"])
        talkback_pending = bool(info.get("talkback_pending"))
        talkback_validation = str(info.get("talkback_validation") or "unknown")
        protocol_name_current = str(info.get("talkback_protocol") or "")
        netsdk_talk = protocol_name_current.startswith("intelbras-netsdk-")
        netsdk_reference = netsdk_talk and str(self.audio_input_preferences.netsdk_talk_mode).startswith("literal-reference")
        if hasattr(self, "netsdk_mode_combo"):
            self.netsdk_mode_combo.setVisible(bool(can_talk and netsdk_talk))
            self.netsdk_mode_label.setVisible(bool(can_talk and netsdk_talk))
            if can_talk and netsdk_talk:
                current_mode = str(self.audio_input_preferences.netsdk_talk_mode or "literal-reference")
                idx = self.netsdk_mode_combo.findData(current_mode)
                if idx >= 0 and idx != self.netsdk_mode_combo.currentIndex():
                    self.netsdk_mode_combo.blockSignals(True)
                    self.netsdk_mode_combo.setCurrentIndex(idx)
                    self.netsdk_mode_combo.blockSignals(False)
        if hasattr(self, "audio_talkback_badge"):
            if can_talk:
                self.audio_talkback_badge.setText("MIC EXP" if talkback_validation == "experimental" else "MIC")
                self.audio_talkback_badge.setToolTip("Retorno de áudio disponível para teste")
                self.audio_talkback_badge.setVisible(True)
            elif talkback_pending:
                pending_protocol = str(info.get("talkback_protocol") or "").replace("-candidate", "")
                netsdk_detail = str(info.get("talkback_netsdk_runtime") or "").strip()
                if pending_protocol.startswith("intelbras-netsdk") and netsdk_detail:
                    self.audio_talkback_badge.setText("MIC INDISP.")
                    detail = f"Talkback Intelbras requer o NetSDK oficial local • {netsdk_detail}"
                else:
                    self.audio_talkback_badge.setText("MIC PEND")
                    detail = "Equipamento anuncia áudio bidirecional, mas o transporte local de retorno ainda não foi homologado"
                    if pending_protocol and pending_protocol not in {"unvalidated", "candidate"}:
                        detail += f" • candidato: {pending_protocol}"
                self.audio_talkback_badge.setToolTip(detail)
                self.audio_talkback_badge.setVisible(True)
            else:
                self.audio_talkback_badge.hide()
        active = bool(tile and self.live_audio_tile_index == tile.index)
        self.listen_audio_btn.setEnabled(can_listen)
        self.listen_audio_btn.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaStop if active else QStyle.StandardPixmap.SP_MediaVolume
            )
        )
        if active:
            self.listen_audio_btn.setToolTip("Parar áudio")
        elif info.get("can_listen"):
            self.listen_audio_btn.setToolTip("Ouvir janela selecionada")
        else:
            self.listen_audio_btn.setToolTip("Verificar e ouvir áudio desta janela")
        self.audio_volume_slider.setEnabled(can_listen)
        capture_available = bool(shutil.which("ffmpeg"))
        mic_ok = bool(self.microphone_inputs) and bool(self.microphone_scan_complete) and capture_available
        if can_talk and not self.microphone_scan_complete and self.microphone_scan_future is None:
            self.refresh_microphone_inputs_async()
        talk_running = self.talkback_session is not None
        if hasattr(self, "microphone_gain_slider"):
            gain_control_enabled = can_talk and not talk_running and not netsdk_reference
            self.set_microphone_gain_controls_enabled(gain_control_enabled)
            if netsdk_reference:
                self.microphone_gain_slider.setToolTip(
                    "O modo NetSDK A1–A3 envia a gravação de referência do demo; selecione B ou C para usar o microfone local."
                )
            else:
                self.microphone_gain_slider.setToolTip(
                    "Ganho independente do microfone antes da codificação • 100% mantém o nível original • "
                    "acima de 100% aplica limitador para proteger contra clipping"
                )
        self.talkback_btn.blockSignals(True)
        self.talkback_btn.setChecked(talk_running)
        if talk_running:
            self.talkback_btn.setText("PARAR")
        elif can_talk:
            self.talkback_btn.setText("MIC")
        elif talkback_pending:
            self.talkback_btn.setText("MIC INDISP.")
        else:
            self.talkback_btn.setText("MIC")
        self.talkback_btn.blockSignals(False)
        self.talkback_btn.setEnabled(talk_running or (can_talk and mic_ok))
        self.talkback_btn.setVisible(can_talk or talkback_pending)
        if talk_running:
            # An active session must remain stoppable after capability loss.
            self.talkback_btn.show()
        if talkback_pending and not can_talk:
            self.talkback_btn.setStyleSheet(
                "QToolButton{color:#e4c887;background:#2a2417;border:1px solid #665329;border-radius:6px;"
                "padding:4px 8px;font-weight:700;}QToolButton:disabled{color:#e4c887;background:#2a2417;border:1px solid #665329;}"
            )
        else:
            self.talkback_btn.setStyleSheet("")
        if hasattr(self, "microphone_row"):
            self.microphone_row.setVisible(can_talk)
        if hasattr(self, "microphone_test_btn"):
            testing = self.microphone_test_future is not None and not self.microphone_test_future.done()
            self.microphone_test_btn.setEnabled(can_talk and mic_ok and not testing and self.talkback_session is None)
        if talk_running:
            talk_tip = "Parar a sessão de microfone ativa"
        elif can_talk and not capture_available:
            talk_tip = "FFmpeg não disponível para capturar o microfone local"
        elif can_talk and not self.microphone_scan_complete:
            talk_tip = "Detectando microfone local em background…"
        elif can_talk and not mic_ok:
            talk_tip = "Microfone local Pulse/PipeWire ou ALSA não disponível"
        elif can_talk:
            mic = self._selected_microphone_input()
            prefix = "Experimental • " if talkback_validation == "experimental" else ""
            protocol_name = str(info.get("talkback_protocol") or "")
            if protocol_name.startswith("intelbras-netsdk-"):
                transport_label = "Intelbras NetSDK"
            elif protocol_name.startswith("intelbras-http-"):
                transport_label = "Intelbras HTTP/G.711A"
            else:
                transport_label = "DVRIP/G.711A"
            talk_tip = f"{prefix}clique para iniciar/parar • {mic.label if mic else 'microfone'} • {transport_label}"
        elif talkback_pending:
            pending_protocol = str(info.get("talkback_protocol") or "")
            netsdk_detail = str(info.get("talkback_netsdk_runtime") or "").strip()
            if pending_protocol.startswith("intelbras-netsdk") and netsdk_detail:
                talk_tip = f"MIC indisponível • NetSDK Intelbras não pronto: {netsdk_detail} • importe em Configuração → Atualizações"
            else:
                talk_tip = "MIC indisponível neste canal • " + str(info.get("talkback_reason") or "retorno local ainda não homologado para este caminho")
        else:
            talk_tip = "Push-to-Talk não homologado"
        self.talkback_btn.setToolTip(talk_tip)
        # Show a compact idle diagnostic only for an exposed talkback path. Runtime
        # status/errors replace it while a session is active.
        if can_talk:
            mic = self._selected_microphone_input()
            mic_name = mic.label if mic else ("detectando microfone…" if not self.microphone_scan_complete else "sem microfone")
            validation_text = "experimental" if talkback_validation == "experimental" else "disponível"
            if not self.microphone_scan_complete and capture_available:
                self.audio_capability_label.setStyleSheet(
                    "color:#aebfb7;background:#111b17;border:1px solid #283a32;border-radius:6px;padding:4px 6px;font-size:9px"
                )
                self.audio_capability_label.setText("MIC aguardando • detectando microfone local…")
            elif not mic_ok:
                self.audio_capability_label.setStyleSheet(
                    "color:#e4c887;background:#241f13;border:1px solid #5a4926;border-radius:6px;padding:4px 6px;font-size:9px;font-weight:700"
                )
                self.audio_capability_label.setText(
                    "MIC INDISPONÍVEL • nenhum microfone local detectado" if capture_available
                    else "MIC INDISPONÍVEL • FFmpeg não disponível para captura"
                )
            else:
                self.audio_capability_label.setStyleSheet(
                    "color:#78a991;background:transparent;border:0;padding:3px 1px;font-size:9px"
                )
                self.audio_capability_label.setText(
                    f"MIC {validation_text} • {mic_name} • ganho {float(self.audio_input_preferences.gain_db):+.1f} dB"
                )
            self.audio_capability_label.show()
        elif talkback_pending:
            self.audio_capability_label.setStyleSheet(
                "color:#e4c887;background:#241f13;border:1px solid #5a4926;border-radius:6px;padding:4px 6px;font-size:9px;font-weight:700"
            )
            pending_protocol = str(info.get("talkback_protocol") or "")
            netsdk_detail = str(info.get("talkback_netsdk_runtime") or "").strip()
            if pending_protocol.startswith("intelbras-netsdk") and netsdk_detail:
                self.audio_capability_label.setText(
                    f"MIC INDISPONÍVEL • NetSDK Intelbras não pronto: {netsdk_detail} • Configuração → Atualizações"
                )
            else:
                self.audio_capability_label.setText(
                    "MIC INDISPONÍVEL NESTE CANAL • retorno local ainda não homologado para este caminho"
                )
            self.audio_capability_label.show()
        else:
            self.audio_capability_label.hide()
        if hasattr(self, "audio_section"):
            self.audio_section.setVisible(can_listen or can_talk or talkback_pending or talk_running)
        trace = self.mic_traces.get(tile.index) if tile else None
        self.mic_progress_label.setVisible(trace is not None)
        if trace is not None:
            self.mic_progress_label.setText(trace.summary())

    def _ptz_context_for_tile(self, tile: VideoTile):
        if tile is None or not tile.source or tile.source.get("type") != "channel":
            return None
        device = self.db.get_device(int(tile.source.get("device_id", 0)))
        channel = self.db.get_recorder_channel(int(tile.source.get("channel_id", 0)))
        if not device or not channel or int(channel["device_id"]) != int(device["id"]):
            return None
        profile_key = self._selected_device_profile_key(device)
        model_text = f"{device['manufacturer']} {device['model']} {device['detected_model']} {device['name']}".lower()
        provider_name = str(device["provider"] or "")
        # 0.2.35: PTZ must reconcile stale generic IT-Blue identities exactly
        # like audio/talkback already does. Older field records may still carry
        # ``it-blue-camera`` even though SpeedDome/X3 evidence is now conclusive.
        profile_key = reconcile_operational_profile_key(
            profile_key=profile_key, provider=provider_name, identity_text=model_text
        )
        if ("it-blue" in f"{provider_name} {device['manufacturer']}".casefold()
                and str(channel["source_name"] or "").casefold().strip() == "lente ptz"
                and "it-blue x3" in str(channel["detail"] or "").casefold()):
            profile_key = "it-blue-x3-we2q"
        known = ptz_capability(provider=provider_name, profile_key=profile_key)
        x3_hint = profile_key == "it-blue-x3-we2q"
        # Generic Web Viewer identities can still have an X3 lens inventory.
        fixed_lens = "lente fixa" in str(channel["source_name"] or "").casefold()
        # X3 has one moving primary lens plus fixed auxiliary views. Primary
        # scope is authoritative even if stale generic metadata once said all.
        ptz_scope = "primary" if x3_hint else str(known.get("scope") or "all")
        scope_ok = not fixed_lens and channel_matches_capability_scope(channel, ptz_scope)
        # Direct PTZ is provider-routed. X3-WE2Q field identity may predate a
        # fully matched AKDB profile, so its known XM/DVRIP transport is used as
        # a conservative fallback only on the primary/PTZ lens.
        if x3_hint and scope_ok and not known.get("backend"):
            known = dict(known)
            known["backend"] = "dvrip"
            known["direct_control"] = True
            known["zoom"] = False
            known["scope"] = "primary"
        # Recorder-mediated Coaxitron/ISAPI PTZ stays visible in Capability Mapping
        # but is not incorrectly sent to a direct-camera endpoint.
        direct_route = str(channel["route_kind"] or "") == "direct"
        supported = bool(scope_ok and direct_route and known.get("direct_control")
                         and known.get("backend") in {"onvif", "dvrip"})
        zoom_supported = bool(supported and known.get("zoom"))
        return device, channel, known, supported, zoom_supported

    def refresh_selected_ptz_controls(self):
        if not hasattr(self, "ptz_buttons"):
            return
        tile = self.selected_video_tile
        ctx = self._ptz_context_for_tile(tile) if tile else None
        enabled = False
        show_section = False
        text = ""
        badge = ""
        if ctx:
            device, _channel, known, supported, zoom_supported = ctx
            creds = self._credentials_for_device(int(device["id"]))
            mode = str(known.get("mode") or "unknown")
            show_section = bool(supported or mode == "recorder-mediated")
            enabled = bool(supported and creds)
            if supported and creds:
                backend = str(known.get("backend") or "onvif").upper()
                text = "PTZ disponível"
                badge = f"PTZ direto • {backend}" + (" • Zoom" if zoom_supported else "")
            elif supported:
                text = "PTZ identificado; salve a credencial para habilitar o controle local."
                badge = "PTZ identificado"
            elif mode == "recorder-mediated":
                text = "PTZ via gravador detectado; controle direto ainda não habilitado."
                badge = "PTZ via gravador"
        if not enabled and getattr(self, "_ptz_active_direction", ""):
            self.stop_selected_ptz_hold()
        for key, btn in self.ptz_buttons.items():
            btn.setEnabled(enabled)
        self.ptz_speed_slider.setEnabled(enabled)
        if hasattr(self, "ptz_section"):
            self.ptz_section.setVisible(show_section)
        self.ptz_capability_badge.setText(badge)
        self.ptz_capability_badge.setVisible(bool(badge))
        self.ptz_status_label.setText(text)
        self.ptz_status_label.setVisible(bool(text))

    def _ptz_target_for_selected(self, direction: str = ""):
        tile = self.selected_video_tile
        ctx = self._ptz_context_for_tile(tile) if tile else None
        if not ctx:
            return None
        device, _channel, known, supported, zoom_supported = ctx
        if not supported or (direction.startswith("zoom") and not zoom_supported):
            return None
        credentials = self._credentials_for_device(int(device["id"]))
        if not credentials:
            self.ptz_status_label.setText("Credencial necessária para PTZ local.")
            self.ptz_status_label.show()
            return None
        # Capture the original endpoint and credentials in memory. A Site/tile
        # switch must never redirect a queued Stop to the newly selected device.
        return {
            "ip": str(device["ip"] or ""), "username": credentials[0], "password": credentials[1],
            "onvif_url": str(device["onvif_url"] or ""), "backend": str(known.get("backend") or ""),
            "speed": max(0.10, min(self.ptz_speed_slider.value() / 100.0, 1.0)),
            "name": str(device["name"] or device["ip"]), "direction": direction,
            "source_key": (tile.index, int(device["id"]), int(tile.source.get("channel_id", 0))),
        }

    def _submit_ptz(self, action: str, direction: str = "", *, quiet: bool = False, target=None):
        if action != "stop" and getattr(self, "_closing_app", False):
            return False
        if action == "start" and getattr(self, "_ptz_command_pending", False):
            return False
        target = target or self._ptz_target_for_selected(direction)
        if not target:
            return False
        # Worker threads consume only captured values, never widgets/selection.
        values = {key: target[key] for key in ("ip", "username", "password", "onvif_url", "speed", "backend")}
        name = target["name"]
        source_key = target["source_key"]
        direction = direction or target["direction"]
        if not quiet:
            self.ptz_status_label.setText("Parando PTZ…" if action == "stop" else f"Movendo: {direction}")
            self.ptz_status_label.show()
        if action == "start":
            self._ptz_command_pending = True

        def run():
            try:
                if action == "stop":
                    message = stop_device_provider(**values, direction=direction)
                elif action == "start":
                    message = start_move_provider(**values, direction=direction)
                else:
                    message = pulse_move_provider(**values, direction=direction)
                self.ptz_results.put((True, name, message, action, source_key))
            except Exception as exc:
                # Transport exceptions can contain URLs/credentials.
                self.ptz_results.put((False, name, type(exc).__name__, action, source_key))
        self.ptz_executor.submit(run)
        return True

    def start_selected_ptz_hold(self, direction: str):
        if getattr(self, "_closing_app", False):
            return
        if not direction or getattr(self, "_ptz_command_pending", False):
            return
        if getattr(self, "_ptz_active_direction", ""):
            self.stop_selected_ptz_hold()
        target = self._ptz_target_for_selected(direction)
        if not target:
            return
        self._ptz_hold_target = target
        self._ptz_last_target = target
        self._ptz_active_direction = direction
        self._ptz_last_direction = direction
        self._submit_ptz("start", direction, target=target)
        self.ptz_hold_timer.start()

    def renew_selected_ptz_hold(self):
        direction = getattr(self, "_ptz_active_direction", "")
        if direction:
            self._submit_ptz("start", direction, quiet=True, target=self._ptz_hold_target)

    def stop_selected_ptz_hold(self):
        target = getattr(self, "_ptz_hold_target", None)
        if target is None:
            target = self._ptz_target_for_selected()
            previous = getattr(self, "_ptz_last_target", None)
            if target and previous and target["source_key"] == previous["source_key"]:
                # DVRIP Stop repeats the original direction/step, including retry.
                target = previous
        self._ptz_active_direction = ""
        self._ptz_hold_target = None
        if hasattr(self, "ptz_hold_timer"):
            self.ptz_hold_timer.stop()
        self._submit_ptz("stop", quiet=True, target=target)

    def move_selected_ptz(self, direction: str):
        # Kept for keyboard/menu compatibility: a bounded pulse remains safe.
        self._submit_ptz("move", direction)

    def stop_selected_ptz(self):
        self.stop_selected_ptz_hold()

    def poll_ptz_results(self):
        while True:
            try:
                ok, name, message, action, source_key = self.ptz_results.get_nowait()
            except Empty:
                break
            if action == "start":
                self._ptz_command_pending = False
            tile = self.selected_video_tile
            source = tile.source if tile and tile.source else {}
            selected_key = (tile.index if tile else -1, int(source.get("device_id", 0)), int(source.get("channel_id", 0)))
            if selected_key != source_key:
                continue
            if not ok and action == "start" and getattr(self, "_ptz_active_direction", ""):
                self.stop_selected_ptz_hold()
            if ok:
                if getattr(self, "_ptz_active_direction", ""):
                    direction_labels = {
                        "up": "cima", "down": "baixo", "left": "esquerda", "right": "direita",
                        "up-left": "cima/esquerda", "up-right": "cima/direita",
                        "down-left": "baixo/esquerda", "down-right": "baixo/direita",
                        "zoom-in": "zoom +", "zoom-out": "zoom −",
                    }
                    self.ptz_status_label.setText(
                        f"Movendo: {direction_labels.get(self._ptz_active_direction, self._ptz_active_direction)}"
                    )
                else:
                    self.ptz_status_label.setText("PTZ disponível")
                self.ptz_status_label.show()
                if self.selected_video_tile is not None:
                    self.append_live_diagnostic(self.selected_video_tile, f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            else:
                self.ptz_status_label.setText(
                    f"PTZ local não respondeu pelo provider selecionado. {message}"
                )
                self.ptz_status_label.show()

    def _audio_identity_text(self, device, channel) -> str:
        try:
            device_name = device_visual_name(device)
        except Exception:
            device_name = str(device["name"] or device["model"] or device["ip"] or "Equipamento")
        try:
            channel_name = self.db.channel_display_name(channel)
        except Exception:
            channel_name = f"CAM {int(channel['channel_no'] or 0):02d}"
        return f"{device_name} • {channel_name}"

    def _set_live_audio_bar(self, state: str = "off", detail: str = ""):
        if not hasattr(self, "bottom_audio"):
            return
        identity = self.live_audio_identity.strip()
        if state == "off" or not identity:
            self.bottom_audio.setText("Áudio: desligado")
            self.bottom_audio.setToolTip("Nenhum canal com áudio de escuta ativo")
            return
        suffix = ""
        if detail:
            suffix = f" • {detail}"
        self.bottom_audio.setText(f"Áudio: {identity}{suffix}")
        self.bottom_audio.setToolTip(f"Áudio de escuta: {identity}" + (f" — {detail}" if detail else ""))

    def stop_live_audio(self):
        self._audio_resume_generation = getattr(self, "_audio_resume_generation", 0) + 1
        session = self.live_audio_session
        if session is not None:
            self._live_audio_previous_session = session
        self.live_audio_session = None
        old_index = self.live_audio_tile_index
        self.live_audio_tile_index = None
        if session is not None:
            session.stop()
        for tile in getattr(self, "video_tiles", []):
            tile.set_audio_active(False)
        if old_index is not None and 0 <= old_index < len(getattr(self, "video_tiles", [])):
            self.append_live_diagnostic(
                self.video_tiles[old_index],
                f"[{datetime.now().strftime('%H:%M:%S')}] Áudio local interrompido.",
            )
        self.live_audio_identity = ""
        self._set_live_audio_bar("off")
        self.refresh_selected_audio_controls()

    def _reset_audio_bar_if_idle(self, generation):
        if (not getattr(self, "_closing_app", False) and self.live_audio_session is None
                and generation == getattr(self, "_audio_resume_generation", 0)):
            self._set_live_audio_bar("off")

    def _resume_audio_after_talkback(self, tile, source, generation, audio_generation):
        if (getattr(self, "_closing_app", False) or tile not in self.video_tiles
                or not source or tile.source != source
                or getattr(tile, "_stream_generation", 0) != generation
                or getattr(self, "_audio_resume_generation", 0) != audio_generation
                or self.talkback_session is not None or self.live_audio_session is not None):
            return
        self.toggle_tile_audio(tile)

    def toggle_tile_audio(self, tile: VideoTile):
        if getattr(self, "_closing_app", False) or tile not in self.video_tiles or not tile.source:
            return
        if self.live_audio_tile_index == tile.index and self.live_audio_session is not None:
            self.stop_live_audio()
            return
        ctx = self._audio_context_for_tile(tile)
        if not ctx:
            return
        device, channel, info, urls = ctx
        if not info["can_listen"] and not info.get("can_probe_listen"):
            QMessageBox.information(self, "Áudio", "Este canal não possui uma rota de áudio disponível para verificação.")
            tile.set_audio_active(False)
            return
        if not urls:
            QMessageBox.information(self, "Áudio", "Não há URL RTSP válida para Main/Sub deste canal.")
            tile.set_audio_active(False)
            return
        credentials = self._credentials_for_device(int(device["id"]))
        if not credentials:
            QMessageBox.information(self, "Áudio", "Configure a credencial do equipamento antes de abrir o áudio.")
            tile.set_audio_active(False)
            return
        previous_audio = self.live_audio_session or getattr(self, "_live_audio_previous_session", None)
        self.stop_live_audio()
        username, password = credentials
        session = create_live_audio_session(
            urls, username, password, volume=self.live_audio_volume, previous_session=previous_audio,
            audio_confirmed=bool(info.get("can_listen")),
            audio_codec=str(channel["audio_codec"] or ""),
            audio_sample_rate=int(channel["audio_sample_rate"] or 0),
        )
        self._live_audio_previous_session = None
        self.live_audio_session = session
        self.live_audio_tile_index = tile.index
        self.live_audio_identity = self._audio_identity_text(device, channel)
        self._set_live_audio_bar("connecting", "conectando…")
        tile.set_audio_active(True)
        self.select_video_tile(tile)
        self.append_live_diagnostic(
            tile,
            f"[{datetime.now().strftime('%H:%M:%S')}] Áudio local solicitado"
            + (f" • {info['label']}" if info.get("label") else "") + ".",
        )
        session.start()
        self.refresh_selected_audio_controls()

    def toggle_selected_tile_audio(self):
        if self.selected_video_tile is not None:
            self.toggle_tile_audio(self.selected_video_tile)

    def _build_live_audio_controls(self, audio_box):
        """Build the compact, aligned listening and microphone controls."""
        shared_slider_style = "QSlider{min-height:20px;}"
        audio_row = QHBoxLayout()
        audio_row.setSpacing(6)
        audio_label = QLabel("Áudio")
        audio_label.setMinimumWidth(62)
        audio_row.addWidget(audio_label)
        self.listen_audio_btn = QToolButton()
        self.listen_audio_btn.setObjectName("ToolbarIconAction")
        self.listen_audio_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        self.listen_audio_btn.setToolTip("Ouvir janela selecionada")
        self.listen_audio_btn.setEnabled(False)
        self.listen_audio_btn.clicked.connect(self.toggle_selected_tile_audio)
        audio_row.addWidget(self.listen_audio_btn)
        self.audio_volume_slider = QSlider(Qt.Horizontal)
        self.audio_volume_slider.setRange(0, 100)
        self.audio_volume_slider.setTracking(True)
        self.audio_volume_slider.setValue(self.live_audio_volume)
        self.audio_volume_slider.setEnabled(False)
        self.audio_volume_slider.setMinimumWidth(0)
        self.audio_volume_slider.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.audio_volume_slider.setStyleSheet(shared_slider_style)
        self.audio_volume_slider.setToolTip("Volume de escuta • curva perceptual • ajuste dinâmico sem reconectar • 0 = mudo • 100 = máximo normal")
        self.audio_volume_slider.valueChanged.connect(self.change_live_audio_volume)
        audio_row.addWidget(self.audio_volume_slider, 1)
        self.audio_volume_value = QLabel(f"{self.live_audio_volume}%")
        self.audio_volume_value.setMinimumWidth(40)
        self.audio_volume_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        audio_row.addWidget(self.audio_volume_value)
        self.talkback_btn = QToolButton()
        self.talkback_btn.setObjectName("ToolbarIconAction")
        self.talkback_btn.setText("MIC")
        self.talkback_btn.setCheckable(True)
        self.talkback_btn.setToolTip("Clique para iniciar/parar o Push-to-Talk")
        self.talkback_btn.setEnabled(False)
        self.talkback_btn.clicked.connect(self.toggle_selected_talkback)
        self.talkback_btn.hide()
        audio_row.addWidget(self.talkback_btn)
        audio_box.addLayout(audio_row)

        self.microphone_row = QWidget()
        mic_outer = QVBoxLayout(self.microphone_row)
        mic_outer.setContentsMargins(0, 0, 0, 0)
        mic_outer.setSpacing(3)
        gain_row = QHBoxLayout()
        gain_row.setSpacing(6)
        gain_label = QLabel("Microfone")
        gain_label.setMinimumWidth(62)
        gain_row.addWidget(gain_label)
        self.microphone_gain_slider = QSlider(Qt.Horizontal)
        self.microphone_gain_slider.setRange(50, 200)
        self.microphone_gain_slider.setValue(microphone_gain_percent_for_db(self.audio_input_preferences.gain_db))
        self.microphone_gain_slider.setEnabled(False)
        self.microphone_gain_slider.setMinimumWidth(0)
        self.microphone_gain_slider.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.microphone_gain_slider.setStyleSheet(shared_slider_style)
        self.microphone_gain_slider.setToolTip(
            "Ganho independente do microfone antes da codificação • 100% mantém o nível original • "
            "acima de 100% aplica limitador para proteger contra clipping"
        )
        self.microphone_gain_slider.valueChanged.connect(self.change_microphone_gain)
        gain_row.addWidget(self.microphone_gain_slider, 1)
        self.microphone_gain_value = QLabel(f"{self.microphone_gain_slider.value()}%")
        self.microphone_gain_value.setMinimumWidth(40)
        self.microphone_gain_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gain_row.addWidget(self.microphone_gain_value)
        self.microphone_gain_reset_btn = QToolButton()
        self.microphone_gain_reset_btn.setObjectName("ToolbarIconAction")
        self.microphone_gain_reset_btn.setText("↺")
        self.microphone_gain_reset_btn.setToolTip("Redefinir ganho do microfone para 100%")
        self.microphone_gain_reset_btn.setEnabled(False)
        self.microphone_gain_reset_btn.clicked.connect(lambda: self.microphone_gain_slider.setValue(100))
        gain_actions = QHBoxLayout()
        gain_actions.setSpacing(5)
        gain_actions.addStretch()
        gain_actions.addWidget(self.microphone_gain_reset_btn)
        self.microphone_test_btn = QToolButton()
        self.microphone_test_btn.setObjectName("ToolbarIconAction")
        self.microphone_test_btn.setText("Testar")
        self.microphone_test_btn.setToolTip("Medir o nível do microfone local sem transmitir para a câmera")
        self.microphone_test_btn.clicked.connect(self.test_selected_microphone_async)
        gain_actions.addWidget(self.microphone_test_btn)
        mic_outer.addLayout(gain_row)
        mic_outer.addLayout(gain_actions)

        device_row = QHBoxLayout()
        device_row.setSpacing(5)
        device_label = QLabel("Dispositivo")
        device_label.setMinimumWidth(62)
        device_label.setStyleSheet("color:#809da8;font-size:9px")
        device_row.addWidget(device_label)
        self.microphone_combo = QComboBox()
        self.microphone_combo.setToolTip("Entrada local usada pelo Push-to-Talk")
        self.microphone_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.microphone_combo.setMinimumContentsLength(8)
        self.microphone_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.microphone_combo.setStyleSheet("font-size:9px;color:#809da8")
        self.microphone_combo.addItem("Detectando microfones…", None)
        self.microphone_combo.currentIndexChanged.connect(self.change_microphone_input)
        device_row.addWidget(self.microphone_combo, 1)
        self.microphone_refresh_btn = QToolButton()
        self.microphone_refresh_btn.setObjectName("ToolbarIconAction")
        self.microphone_refresh_btn.setText("↻")
        self.microphone_refresh_btn.setToolTip("Atualizar lista de microfones")
        self.microphone_refresh_btn.clicked.connect(lambda: self.refresh_microphone_inputs_async(force=True))
        device_row.addWidget(self.microphone_refresh_btn)
        mic_outer.addLayout(device_row)

        netsdk_row = QHBoxLayout()
        netsdk_row.setSpacing(5)
        self.netsdk_mode_label = QLabel("PTT:")
        self.netsdk_mode_label.setMinimumWidth(62)
        netsdk_row.addWidget(self.netsdk_mode_label)
        self.netsdk_mode_combo = QComboBox()
        self.netsdk_mode_combo.addItem("A1 • Demo 05.Talk literal", "literal-reference")
        self.netsdk_mode_combo.addItem("A2 • Demo + aguardar dispositivo", "literal-reference-wait")
        self.netsdk_mode_combo.addItem("A3 • Demo + speaker 1", "literal-reference-speaker1")
        self.netsdk_mode_combo.addItem("B • C270 PCM / handshake literal", "live-pcm-literal")
        self.netsdk_mode_combo.addItem("C • C270 G.711A 8 kHz", "live-g711a-server")
        mode_index = self.netsdk_mode_combo.findData(str(self.audio_input_preferences.netsdk_talk_mode))
        self.netsdk_mode_combo.setCurrentIndex(max(0, mode_index))
        self.netsdk_mode_combo.setToolTip(
            "Diagnóstico NetSDK 0.2.42. A1 replica literalmente o demo 05.Talk; A2 muda apenas bEnableWait; "
            "A3 muda apenas o canal do speaker. B/C ficam como comparação do microfone ao vivo."
        )
        self.netsdk_mode_combo.setMinimumContentsLength(8)
        self.netsdk_mode_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.netsdk_mode_combo.setStyleSheet("font-size:9px")
        self.netsdk_mode_combo.currentIndexChanged.connect(self.change_netsdk_talk_mode)
        netsdk_row.addWidget(self.netsdk_mode_combo, 1)
        self.netsdk_mode_label.hide()
        self.netsdk_mode_combo.hide()
        mic_outer.addLayout(netsdk_row)
        self.microphone_row.hide()
        audio_box.addWidget(self.microphone_row)

    def change_live_audio_volume(self, value: int):
        self.live_audio_volume = max(0, min(int(value), 100))
        if hasattr(self, "audio_volume_value"):
            self.audio_volume_value.setText(f"{self.live_audio_volume}%")
        session = self.live_audio_session
        expected = self.live_audio_volume
        if session is not None:
            # Coalesce rapid slider events while keeping the current RTSP player
            # alive. 0.2.24 restarted the process here, which looked like a freeze.
            QTimer.singleShot(80, lambda v=expected, s=session: self._apply_audio_volume_if_current(s, v))

    def _apply_audio_volume_if_current(self, session: LiveAudioSession, value: int):
        if session is self.live_audio_session and value == self.live_audio_volume:
            session.set_volume(value)

    def _talkback_context_for_tile(self, tile: VideoTile):
        ctx = self._audio_context_for_tile(tile)
        if not ctx:
            return None
        device, channel, info, urls = ctx
        protocol = str(info.get("talkback_protocol") or "")
        return device, channel, info, urls, protocol

    def start_talkback_for_tile(self, tile: VideoTile):
        if getattr(self, "_closing_app", False) or tile not in self.video_tiles or not tile.source:
            return
        if self.talkback_session is not None:
            return
        ctx = self._talkback_context_for_tile(tile)
        if not ctx:
            return
        device, _channel, info, _urls, protocol = ctx
        microphone = self._selected_microphone_input()
        credentials = self._credentials_for_device(int(device["id"]))
        readiness = talkback_start_readiness(
            info, microphone=microphone, scan_complete=self.microphone_scan_complete,
            credentials=credentials, ffmpeg_available=bool(shutil.which("ffmpeg")),
        )
        if not readiness.ready:
            if readiness.code == "microphone_scanning":
                self.refresh_microphone_inputs_async()
            QMessageBox.information(self, "Push-to-Talk", readiness.detail)
            return
        username, password = credentials
        self._talkback_resume_audio = bool(self.live_audio_tile_index == tile.index and self.live_audio_session is not None)
        if self.live_audio_session is not None:
            self.stop_live_audio()
        if protocol == "intelbras-netsdk-talk-experimental":
            session = IntelbrasNetSDKTalkbackSession(
                device["ip"], username, password,
                candidate_ports=list(info.get("talkback_netsdk_ports") or [37777, 37778, 34567]),
                microphone_backend=microphone.backend,
                microphone_source=microphone.source,
                microphone_label=microphone.label,
                gain_db=float(self.audio_input_preferences.gain_db),
                channel_index=0,
                test_mode=str(self.audio_input_preferences.netsdk_talk_mode or "literal-reference"),
            )
            mode_label = {
                "literal-reference": "Teste A1/demo literal",
                "literal-reference-wait": "Teste A2/aguardar dispositivo",
                "literal-reference-speaker1": "Teste A3/speaker 1",
                "live-pcm-literal": "Teste B/C270 PCM literal",
                "live-g711a-server": "Teste C/C270 G.711A",
            }.get(str(self.audio_input_preferences.netsdk_talk_mode), "matriz NetSDK")
            transport_text = f"Intelbras NetSDK oficial • {mode_label}"
        elif protocol == "intelbras-http-postaudio-experimental":
            session = IntelbrasHttpTalkbackSession(
                device["ip"], username, password,
                base_url=str(info.get("talkback_base_url") or f"http://{device['ip']}"),
                audio_channel=int(info.get("talkback_audio_channel") or 1),
                microphone_backend=microphone.backend,
                microphone_source=microphone.source,
                microphone_label=microphone.label,
                gain_db=float(self.audio_input_preferences.gain_db),
            )
            transport_text = "Intelbras HTTP postAudio/G.711A"
        else:
            session = XmDvripTalkbackSession(
                device["ip"], username, password,
                microphone_backend=microphone.backend,
                microphone_source=microphone.source,
                microphone_label=microphone.label,
                gain_db=float(self.audio_input_preferences.gain_db),
            )
            transport_text = "DVRIP/G.711A"
        self.talkback_session = session
        self.talkback_tile_index = tile.index
        self.mic_traces[tile.index] = MicTrace()
        self._update_mic_trace(tile.index, "MIC solicitado")
        self.select_video_tile(tile)
        self.audio_capability_label.setText("Abrindo Push-to-Talk…")
        self.audio_capability_label.show()
        self.append_live_diagnostic(
            tile, f"[{datetime.now().strftime('%H:%M:%S')}] Push-to-Talk solicitado • {transport_text} • "
            f"{microphone.label} • MIC {microphone_gain_percent_for_db(self.audio_input_preferences.gain_db)}%.",
        )
        session.start()

    def stop_talkback(self):
        session = self.talkback_session
        if session is not None:
            session.stop()
            if hasattr(self, "audio_capability_label"):
                self.audio_capability_label.setText("Encerrando talkback…")

    def start_selected_talkback(self):
        if self.selected_video_tile is not None:
            self.start_talkback_for_tile(self.selected_video_tile)

    def stop_selected_talkback(self):
        self.stop_talkback()

    def toggle_selected_talkback(self, checked: bool = False):
        """Click-to-talk UX with a hard session limit in the active talkback transport.

        This replaces the fragile mouse press/release timing used up to 0.2.32;
        a click starts the experimental session and a second click stops it.
        """
        if self.talkback_session is not None:
            self.stop_talkback()
            return
        if self.selected_video_tile is not None:
            self.start_talkback_for_tile(self.selected_video_tile)
        self.refresh_selected_audio_controls()

    def show_talkback_info(self, tile: VideoTile):
        ctx = self._talkback_context_for_tile(tile)
        if not ctx:
            return
        device, _channel, info, _url, protocol = ctx
        detail = str(info.get("talkback_reason") or TALKBACK_REASONS["no_capability"])
        if info.get("can_talk"):
            transport = talkback_transport(protocol)
            label = transport.label if transport else "não implementado"
            detail = (f"{device['name']} • {label} • experimental. " + detail
                      + " Use MIC para iniciar/parar. A sessão possui limite automático de segurança.")
        QMessageBox.information(self, "Push-to-Talk", detail)

    def show_selected_talkback_info(self):
        if self.selected_video_tile is not None:
            self.show_talkback_info(self.selected_video_tile)

    def change_selected_channel_stream(self):
        if self._stream_combo_sync or not self.selected_channel_context:
            return
        _device_id, channel_id = self.selected_channel_context
        preferred = self.stream_combo.currentData() or "auto"
        self.db.update_channel_preferred_stream(channel_id, preferred)
        for tile in self.video_tiles:
            if tile.source and tile.source.get("channel_id") == channel_id:
                source = dict(tile.source)
                self.apply_source_to_tile(tile, source)
        self.refresh_source_tree(self.db.list_sites(), self.db.list_devices(None))
        self.save_live_workspace()

    @requires_permission('device_edit')
    def rename_selected_channel(self):
        if not self.selected_channel_context:
            return
        device_id, channel_id = self.selected_channel_context
        channel = self.db.get_recorder_channel(channel_id)
        if not channel:
            return
        current = channel["alias"] or ""
        source_name = channel["source_name"] or channel["name"] or f"Canal {channel['channel_no']:02d}"
        alias, ok = QInputDialog.getText(
            self,
            "Nome da câmera / canal",
            f"Nome informado pelo gravador: {source_name}\nApelido no Sentinel (vazio = usar nome do gravador):",
            QLineEdit.Normal,
            current,
        )
        if not ok:
            return
        self.db.update_channel_alias(channel_id, alias)
        self.refresh_all()
        for tile in self.video_tiles:
            if tile.source and tile.source.get("channel_id") == channel_id:
                updated = self.db.get_recorder_channel(channel_id)
                tile.header.setText(self.db.channel_display_name(updated))
                tile.source["title"] = self.db.channel_display_name(updated)

    def toggle_live_diagnostics(self, visible: bool):
        self.live_diag_panel.setVisible(bool(visible))
        if visible:
            self.refresh_live_diagnostic_panel()

    def append_live_diagnostic(self, tile: VideoTile, line: str):
        from .runtime_diagnostics import record_runtime
        record_runtime(self, "ao vivo", line)
        lines = self.live_diag_lines.setdefault(tile.index, [])
        lines.append(line)
        if len(lines) > 80:
            del lines[:-80]
        if self.live_diag_panel.isVisible() and tile is self.selected_video_tile:
            self.live_diag_panel.appendPlainText(line)

    def refresh_live_diagnostic_panel(self):
        self.live_diag_panel.clear()
        tile = self.selected_video_tile
        if tile is None:
            self.live_diag_panel.setPlainText("Nenhuma janela selecionada.")
            return
        source = tile.source or {}
        title = source.get("title", f"Janela {tile.index + 1}")
        active = source.get("active_stream", "—")
        self.live_diag_panel.appendPlainText(f"Janela {tile.index + 1} — {title}")
        self.live_diag_panel.appendPlainText(f"Stream ativo: {active}")
        self.live_diag_panel.appendPlainText("Credenciais e URLs autenticadas são ocultadas por segurança.")
        if source.get("device_id"):
            self.append_camera_event_diagnostic(source["device_id"])
        media = local_media_status()
        audio = self.live_audio_session if self.live_audio_tile_index == tile.index else None
        if audio is not None:
            self.live_diag_panel.appendPlainText(f"Estado atual do áudio: {audio.current_state_text()}\n")
        else:
            self.live_diag_panel.appendPlainText("Estado atual do áudio: desligado\n")
        self.live_diag_panel.appendPlainText(
            "Decoders locais: "
            f"H.264={'OK' if media['h264'] else 'ausente'} • "
            f"HEVC={'OK' if media['hevc'] else 'ausente'} • "
            f"AAC={'OK' if media['aac'] else 'ausente'} • "
            f"G.711u={'OK' if media['g711u'] else 'ausente'} • "
            f"G.711a={'OK' if media['g711a'] else 'ausente'}\n"
            "Saída de áudio: "
            f"ffplay={'OK' if media['ffplay'] else 'ausente'} • "
            f"Pulse/PipeWire={'OK' if media.get('audio_output_pulse') else 'ausente'} • "
            f"ALSA={'OK' if media.get('audio_output_alsa') else 'ausente'} • "
            f"volume dinâmico={'OK' if media.get('dynamic_audio_volume') else 'indisponível'}\n"
        )
        for line in self.live_diag_lines.get(tile.index, []):
            self.live_diag_panel.appendPlainText(line)

    def show_source_context_menu(self, pos):
        item = self.source_tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        menu = QMenu(self)
        if data[0] == "device":
            device_id = int(data[1])
            open_all = QAction("Abrir todos os canais", self)
            open_all.triggered.connect(lambda: self.open_all_device_channels(device_id))
            menu.addAction(open_all)
            menu.popup(self.source_tree.viewport().mapToGlobal(pos))
            self._source_context_menu = menu
            return
        if data[0] != "channel":
            return
        device_id, channel_id = int(data[1]), int(data[2])
        open_action = QAction("Abrir aqui (modo salvo)", self)
        open_action.triggered.connect(lambda: self.open_channel_with_stream(device_id, channel_id, None))
        menu.addAction(open_action)
        stream_menu = menu.addMenu("Abrir com stream")
        for label, mode in (("Automático", "auto"), ("Substream", "sub"), ("Main stream", "main")):
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, m=mode: self.open_channel_with_stream(device_id, channel_id, m))
            stream_menu.addAction(act)
        menu.addSeparator()
        rename_action = QAction("Renomear câmera / canal", self)
        rename_action.triggered.connect(lambda: self.rename_channel_by_id(device_id, channel_id))
        menu.addAction(rename_action)
        diag_action = QAction("Diagnóstico", self)
        diag_action.triggered.connect(lambda: self.open_channel_diagnostics(channel_id))
        menu.addAction(diag_action)
        menu.popup(self.source_tree.viewport().mapToGlobal(pos))
        self._source_context_menu = menu

    def show_tile_context_menu(self, tile: VideoTile, pos):
        self.select_video_tile(tile)
        menu = QMenu(self)
        if tile.source and tile.source.get("type") == "channel":
            channel_id = int(tile.source["channel_id"])
            device_id = int(tile.source["device_id"])

            menu.addSection("VISUALIZAÇÃO")
            stream_menu = menu.addMenu("Stream")
            active_kind = str(tile.source.get("active_stream") or "")
            for label, mode in (("Automático", "auto"), ("Substream", "sub"), ("Main stream", "main")):
                act = QAction(label, self)
                act.setCheckable(True)
                act.setChecked(mode == active_kind or (mode == "auto" and not active_kind))
                act.triggered.connect(lambda checked=False, m=mode: self.change_tile_stream(tile, m))
                stream_menu.addAction(act)
            fit_menu = menu.addMenu("Enquadramento")
            for label, mode in (("Preencher (sem esticar)", "fill"), ("Ajustar / imagem inteira", "fit"), ("Original / 1:1", "original")):
                act = QAction(label, self)
                act.setCheckable(True)
                act.setChecked(tile.display_mode == mode)
                act.triggered.connect(lambda checked=False, m=mode: self.change_tile_display_mode(tile, m))
                fit_menu.addAction(act)
            full = QAction("Tela cheia desta câmera", self)
            full.triggered.connect(lambda: self.focus_video_tile(tile))
            menu.addAction(full)
            full_mosaic = QAction("Tela cheia do mosaico", self)
            full_mosaic.triggered.connect(self.toggle_primary_mosaic_fullscreen)
            menu.addAction(full_mosaic)

            menu.addSection("ÁUDIO")
            ctx = self._audio_context_for_tile(tile)
            info = ctx[2] if ctx else {"can_listen": False, "can_probe_listen": False, "can_talk": False, "talkback_pending": False}
            can_listen = bool(info.get("can_listen") or info.get("can_probe_listen"))
            audio_active = self.live_audio_tile_index == tile.index
            if audio_active:
                audio_label = "Parar áudio  •  ATIVO"
            elif can_listen:
                audio_label = "Ouvir áudio"
            else:
                audio_label = "Ouvir áudio  —  indisponível"
            audio_action = QAction(audio_label, self)
            audio_action.setEnabled(can_listen)
            audio_action.triggered.connect(lambda: self.toggle_tile_audio(tile))
            menu.addAction(audio_action)

            can_talk = bool(info.get("can_talk"))
            pending = bool(info.get("talkback_pending"))
            if can_talk:
                protocol = str(info.get("talkback_protocol") or "")
                suffix = "  •  NetSDK EXP" if protocol.startswith("intelbras-netsdk") else "  •  EXP" if str(info.get("talkback_validation")) == "experimental" else ""
                talk_action = QAction("Push-to-Talk" + suffix, self)
                talk_action.triggered.connect(lambda: self.show_talkback_info(tile))
                menu.addAction(talk_action)
            else:
                talk_action = QAction("Push-to-Talk  —  INDISPONÍVEL", self)
                talk_action.setEnabled(False)
                menu.addAction(talk_action)
                reason = "Talkback não homologado para este canal"
                protocol = str(info.get("talkback_protocol") or "")
                netsdk_detail = str(info.get("talkback_netsdk_runtime") or "").strip()
                if pending and protocol.startswith("intelbras-netsdk"):
                    reason = "NetSDK Intelbras necessário" + (f" • {netsdk_detail}" if netsdk_detail else "")
                elif pending:
                    reason = "Transporte de retorno ainda não homologado"
                reason_action = QAction("↳ " + reason, self)
                reason_action.setEnabled(False)
                menu.addAction(reason_action)

            diag = QAction("Diagnóstico do Live View / áudio", self)
            diag.triggered.connect(lambda: self.show_diagnostics_for_tile(tile))
            menu.addAction(diag)

            menu.addSection("CANAL")
            rename = QAction("Renomear câmera / canal", self)
            rename.triggered.connect(lambda: self.rename_channel_by_id(device_id, channel_id))
            menu.addAction(rename)
            if live_session_can_pause_reconnect(self.live_sessions.get(tile.index)):
                reconnect = QAction("Pausar reconexão automática", self)
                reconnect.triggered.connect(lambda: self.pause_tile_reconnect(tile))
            else:
                reconnect = QAction("Retomar conexão", self)
                reconnect.triggered.connect(lambda: self.change_tile_stream(tile, str(tile.source.get("active_stream") or "auto")))
            menu.addAction(reconnect)
            menu.addSeparator()
        remove = QAction("Fechar canal", self)
        remove.triggered.connect(lambda: self.close_tile_source(tile))
        menu.addAction(remove)
        menu.popup(tile.mapToGlobal(pos))
        self._tile_context_menu = menu

    def _restore_mosaic_after_focused_close(self, closed_tile: VideoTile):
        """Leave camera focus safely after the focused tile is closed.

        Existing FFmpeg sessions are preserved: only Qt tile geometry/visibility
        is restored, then selection moves to another populated tile or the next
        available slot. This path is shared by the tile X and context-menu close.
        """
        self._focus_return_state = None
        self._restore_video_grid_geometry()
        candidates = [t for t in self.video_tiles if t is not closed_tile and t.source]
        if not candidates:
            candidates = [t for t in self.video_tiles if t is not closed_tile]
        if not candidates and self.video_tiles:
            candidates = [self.video_tiles[0]]
        if candidates:
            self.select_video_tile(candidates[0])
        else:
            self.selected_video_tile = None

    def close_tile_source(self, tile: VideoTile):
        """Close one tile, restoring the mosaic first when it was focused."""
        focused = bool(self._focus_return_state is not None and int(self._focus_return_state.get("tile_index", -1)) == int(tile.index))
        self.stop_tile_stream(tile)
        tile.clear_source()
        self.live_diag_lines.pop(tile.index, None)
        if focused:
            self._restore_mosaic_after_focused_close(tile)
        if self.selected_video_tile is tile:
            self._set_live_selection_summary("Janela vazia", "Canal fechado individualmente.")
            self.stream_combo.setEnabled(False)
            self.rename_channel_action.setEnabled(False)
        self.save_live_workspace()
        if self.live_diag_panel.isVisible():
            self.refresh_live_diagnostic_panel()

    def pause_tile_reconnect(self, tile: VideoTile):
        """Stop the live worker but keep source identity/diagnostics visible."""
        self.stop_tile_stream(tile)
        if tile.source:
            tile.footer.setText("Reconexão pausada • botão direito para reabrir")
            self.live_diag_lines.setdefault(tile.index, []).append(
                f"[{datetime.now().strftime('%H:%M:%S')}] Reconexão pausada manualmente pelo operador."
            )
        if self.live_diag_panel.isVisible():
            self.refresh_live_diagnostic_panel()

    def show_diagnostics_for_tile(self, tile: VideoTile):
        self.select_video_tile(tile)
        self.diag_toggle.setChecked(True)
        self.refresh_live_diagnostic_panel()

    def open_channel_diagnostics(self, channel_id: int):
        for tile in self.video_tiles:
            if tile.source and int(tile.source.get("channel_id", -1)) == int(channel_id):
                self.show_diagnostics_for_tile(tile)
                return
        self.diag_toggle.setChecked(True)
        self.live_diag_panel.setPlainText("Este canal ainda não está aberto no mosaico. Abra-o para coletar diagnóstico do Live View.")

    def remove_tile_source(self, tile: VideoTile):
        self.close_tile_source(tile)

    def change_tile_stream(self, tile: VideoTile, mode: str):
        if not tile.source or tile.source.get("type") != "channel":
            return
        listening = self.live_audio_tile_index == tile.index and self.live_audio_session is not None
        channel_id = int(tile.source["channel_id"])
        self.db.update_channel_preferred_stream(channel_id, mode)
        source = dict(tile.source)
        source["forced_stream"] = mode if mode != "auto" else None
        if source.get("forced_stream") is None:
            source.pop("forced_stream", None)
        self.apply_source_to_tile(tile, source)
        if listening and tile.index in self.live_sessions:
            self.toggle_tile_audio(tile)
        self.save_live_workspace()
        self.refresh_source_tree(self.db.list_sites(), self.db.list_devices(None))

    def change_tile_display_mode(self, tile: VideoTile, mode: str):
        if tile is None:
            return
        tile.set_display_mode(mode)
        if isinstance(tile.source, dict):
            tile.source["display_mode"] = tile.display_mode
        labels = {"fill": "Preencher", "fit": "Ajustar", "original": "Original / 1:1"}
        self.bottom_notice.setText(f"Enquadramento: {labels.get(tile.display_mode, tile.display_mode)}")
        QTimer.singleShot(1800, lambda: self.bottom_notice.setText("") if self.bottom_notice.text().startswith("Enquadramento:") else None)
        self.save_live_workspace()

    def open_channel_with_stream(self, device_id: int, channel_id: int, mode: str | None):
        self._open_channel_in_selected_and_advance(device_id, channel_id, mode)

    def rename_channel_by_id(self, device_id: int, channel_id: int):
        self.selected_channel_context = (int(device_id), int(channel_id))
        self.rename_selected_channel()

    def save_live_workspace(self, *_args):
        if getattr(self, "_suspend_workspace_save", False) or not self.current_site_id or not hasattr(self, "video_tiles"):
            return
        slots = self._live_slots_snapshot()
        ask = bool(self.ask_stream_check.isChecked()) if hasattr(self, "ask_stream_check") else False
        try:
            self.db.save_live_workspace(self.current_site_id, len(self.video_tiles) or 4, slots, ask)
        except Exception:
            pass

    def _live_slots_snapshot(self):
        slots = []
        for tile in self.video_tiles:
            source = tile.source
            if not source or source.get("type") != "channel":
                slots.append({})
                continue
            slots.append({
                "type": "channel",
                "device_id": int(source.get("device_id")),
                "channel_id": int(source.get("channel_id")),
                "forced_stream": source.get("forced_stream") or "",
                "display_mode": source.get("display_mode") or tile.display_mode,
            })
        return slots

    def refresh_live_presets(self):
        if not hasattr(self, "preset_combo"):
            return
        previous = self.preset_combo.currentData()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Rotinas salvas", "")
        if self.current_site_id:
            for row in self.db.list_live_presets(self.current_site_id):
                self.preset_combo.addItem(row["name"], row["name"])
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(previous)))
        self.preset_combo.blockSignals(False)

    def save_named_live_preset(self):
        if not self.current_site_id:
            return
        name, ok = QInputDialog.getText(self, "Salvar rotina", "Nome da rotina de observação:",
                                        text=str(self.preset_combo.currentData() or ""))
        name = name.strip()
        if not ok or not name:
            return
        if len(name) > 64:
            QMessageBox.warning(self, "Nome longo", "Use até 64 caracteres.")
            return
        if self.db.load_live_preset(self.current_site_id, name):
            if QMessageBox.question(self, "Substituir rotina", f"Substituir a rotina ‘{name}’ pelo mosaico atual?") != QMessageBox.Yes:
                return
        self.db.save_live_preset(self.current_site_id, name, len(self.video_tiles), self._live_slots_snapshot())
        self.refresh_live_presets()
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(name))
        self.bottom_notice.setText(f"Rotina ‘{name}’ salva")

    def load_selected_live_preset(self, _index):
        name = self.preset_combo.currentData()
        if not name or not self.current_site_id:
            return
        state = self.db.load_live_preset(self.current_site_id, name)
        if not state:
            self.refresh_live_presets()
            return
        count = state["grid_count"]
        if self.layout_combo.findData(count) < 0:
            return
        self._suspend_workspace_save = True
        try:
            self.clear_video_grid_sources()
            self.layout_combo.blockSignals(True)
            self.layout_combo.setCurrentIndex(self.layout_combo.findData(count))
            self.layout_combo.blockSignals(False)
            self.rebuild_video_grid(count)
        finally:
            self._suspend_workspace_save = False
        missing = 0
        for tile, saved in zip(self.video_tiles, state["slots"]):
            if not isinstance(saved, dict) or saved.get("type") != "channel":
                continue
            try:
                device_id, channel_id = int(saved["device_id"]), int(saved["channel_id"])
            except (ValueError, TypeError, KeyError):
                missing += 1
                continue
            device = self.db.get_device(device_id)
            channel = self.db.get_recorder_channel(channel_id)
            if not device or not channel or int(channel["device_id"]) != device_id or int(device["site_id"] or 0) != self.current_site_id:
                missing += 1
                continue
            source = {"type": "channel", "device_id": device_id, "channel_id": channel_id,
                      "display_mode": saved.get("display_mode") or "fill"}
            if saved.get("forced_stream") in {"main", "sub"}:
                source["forced_stream"] = saved["forced_stream"]
            self.apply_source_to_tile(tile, source)
        self.save_live_workspace()
        self.bottom_notice.setText(f"Rotina ‘{name}’ carregada" + (f" • {missing} canal(is) indisponíveis" if missing else ""))

    def delete_selected_live_preset(self):
        name = self.preset_combo.currentData()
        if not name or not self.current_site_id:
            return
        if QMessageBox.question(self, "Excluir rotina", f"Excluir a rotina ‘{name}’?") != QMessageBox.Yes:
            return
        self.db.delete_live_preset(self.current_site_id, name)
        self.refresh_live_presets()

    @requires_permission('export')
    def save_live_photo(self):
        tile = self.selected_video_tile
        pixmap = tile.body.pixmap() if tile and tile.source else None
        if pixmap is None or pixmap.isNull():
            QMessageBox.information(self, "Foto", "Selecione um canal com imagem ao vivo.")
            return
        suggested = f"Sentinel-foto-{datetime.now():%Y%m%d-%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar foto", suggested, "Imagem PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if os.path.exists(path):
            QMessageBox.warning(self, "Foto", "O arquivo já existe. Escolha outro nome.")
            return
        if not pixmap.save(path, "PNG"):
            QMessageBox.warning(self, "Foto", "Não foi possível salvar a foto.")
        else:
            self.bottom_notice.setText(f"Foto salva: {path}")

    def toggle_manual_recording(self):
        recording = self.manual_recording
        if recording is not None:
            if not recording.finished:
                recording.stop()
                self.bottom_notice.setText("Finalizando MP4…")
            return
        if not authorize(self,'record'):return
        tile = self.selected_video_tile
        if not tile or not tile.source or tile.index not in self.live_sessions:
            QMessageBox.information(self, "Gravação", "Selecione um canal com vídeo ao vivo.")
            return
        session = self.live_sessions[tile.index]
        url = session.fallback_url if session.active_profile == session.fallback_name else session.url
        if not str(url).lower().startswith("rtsp://"):
            QMessageBox.information(self, "Gravação", "Gravação rápida disponível para streams RTSP. Use a reprodução do gravador para este canal.")
            return
        suggested = f"Sentinel-video-{datetime.now():%Y%m%d-%H%M%S}.mp4"
        path, _ = QFileDialog.getSaveFileName(self, "Gravar vídeo ao vivo", suggested, "Vídeo MP4 (*.mp4)")
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        recording = ManualRecording(url, session.username, session.password, path)
        try:
            recording.start()
        except ValueError as exc:
            QMessageBox.warning(self, "Gravação", str(exc))
            return
        self.manual_recording = recording
        self.record_button.setText("■")
        self.record_button.setToolTip("Parar gravação e finalizar MP4")
        self.bottom_notice.setText("● Gravação iniciada • clique em ■ para salvar")
        QTimer.singleShot(500, self.poll_manual_recording)

    def poll_manual_recording(self):
        recording = self.manual_recording
        if recording is None:
            return
        if not recording.finished:
            if not self._closing_app:
                QTimer.singleShot(500, self.poll_manual_recording)
            return
        self.manual_recording = None
        self.record_button.setText("●")
        self.record_button.setToolTip("Iniciar gravação do canal selecionado")
        if recording.saved:
            self.bottom_notice.setText(f"Vídeo salvo: {recording.destination}")
        else:
            QMessageBox.warning(self, "Gravação", recording.error or "Não foi possível salvar o MP4.")

    def restore_live_workspace(self):
        if not self.current_site_id or not hasattr(self, "layout_combo"):
            return
        self.refresh_live_presets()
        state = self.db.load_live_workspace(self.current_site_id)
        if not state:
            self._suspend_workspace_save = True
            try:
                self.clear_video_grid_sources()
            finally:
                self._suspend_workspace_save = False
            self._workspace_restored_site = self.current_site_id
            return
        count = int(state.get("grid_count") or 4)
        idx = self.layout_combo.findData(count)
        if idx >= 0:
            self.layout_combo.blockSignals(True)
            self.layout_combo.setCurrentIndex(idx)
            self.layout_combo.blockSignals(False)
        self._suspend_workspace_save = True
        try:
            self.clear_video_grid_sources()
            self.rebuild_video_grid(count)
        finally:
            self._suspend_workspace_save = False
        ask_stream = bool(state.get("ask_stream"))
        self.ask_stream_check.blockSignals(True)
        self.ask_stream_check.setChecked(ask_stream)
        self.ask_stream_check.blockSignals(False)
        self.ask_stream_action.blockSignals(True)
        self.ask_stream_action.setChecked(ask_stream)
        self.ask_stream_action.blockSignals(False)
        for tile, saved in zip(self.video_tiles, state.get("slots") or []):
            if not saved or saved.get("type") != "channel":
                continue
            if not self.db.get_device(int(saved.get("device_id", 0))):
                continue
            if not self.db.get_recorder_channel(int(saved.get("channel_id", 0))):
                continue
            source = {
                "type": "channel",
                "device_id": int(saved["device_id"]),
                "channel_id": int(saved["channel_id"]),
                "display_mode": saved.get("display_mode") or "fill",
            }
            forced = saved.get("forced_stream") or ""
            if forced in {"main", "sub"}:
                source["forced_stream"] = forced
            self.apply_source_to_tile(tile, source)
        self._workspace_restored_site = self.current_site_id

    # ---------- playback ----------
    def build_playback_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("REPRODUÇÃO REMOTA")
        f = QFont(); f.setPointSize(16); f.setBold(True); title.setFont(f)
        header.addWidget(title)
        header.addStretch()
        self.playback_web_button = QPushButton("Abrir no gravador ↗")
        self.playback_web_button.clicked.connect(self.open_playback_device_web)
        header.addWidget(self.playback_web_button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        sidebar = QFrame()
        sidebar.setObjectName("VideoTile")
        sidebar.setMinimumWidth(280)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 12, 12, 12)
        side.setSpacing(9)
        source_label = QLabel("FONTE DA GRAVAÇÃO")
        source_label.setStyleSheet("color:#37c8e8;font-weight:700")
        side.addWidget(source_label)
        side.addWidget(QLabel("Gravador"))
        self.playback_device_combo = QComboBox()
        self.playback_device_combo.currentIndexChanged.connect(self.refresh_playback_channels)
        side.addWidget(self.playback_device_combo)
        side.addWidget(QLabel("Canal"))
        self.playback_channel_combo = QComboBox()
        self.playback_channel_combo.currentIndexChanged.connect(self.clear_playback_results)
        side.addWidget(self.playback_channel_combo)
        self.playback_multi_check = QCheckBox("Comparar até 4 câmeras")
        self.playback_multi_check.toggled.connect(self.toggle_playback_multi)
        side.addWidget(self.playback_multi_check)
        self.playback_channel_list = QListWidget()
        self.playback_channel_list.setMaximumHeight(110)
        self.playback_channel_list.itemChanged.connect(self.playback_channel_checked)
        self.playback_channel_list.hide()
        side.addWidget(self.playback_channel_list)
        self.playback_access_note = QLabel("")
        self.playback_access_note.setWordWrap(True)
        self.playback_access_note.setStyleSheet("color:#a4bdc3")
        side.addWidget(self.playback_access_note)

        period_label = QLabel("PERÍODO")
        period_label.setStyleSheet("color:#37c8e8;font-weight:700")
        side.addWidget(period_label)
        side.addWidget(QLabel("Início"))
        from .recording_history_ui import RecordingDateEdit
        self.playback_start = RecordingDateEdit(QDateTime.currentDateTime().addSecs(-3600))
        self.playback_start.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.playback_start.setCalendarPopup(True)
        self.playback_start.dateTimeChanged.connect(self.clear_playback_results)
        side.addWidget(self.playback_start)
        side.addWidget(QLabel("Fim"))
        self.playback_end = RecordingDateEdit(QDateTime.currentDateTime())
        self.playback_end.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.playback_end.setCalendarPopup(True)
        self.playback_end.dateTimeChanged.connect(self.clear_playback_results)
        side.addWidget(self.playback_end)
        from .recording_history_ui import add_history_controls
        add_history_controls(self, side)
        self.playback_search_btn = QPushButton("Buscar gravações")
        self.playback_search_btn.clicked.connect(self.search_playback_recordings)
        side.addWidget(self.playback_search_btn)

        result_label = QLabel("TRECHOS ENCONTRADOS")
        result_label.setStyleSheet("color:#37c8e8;font-weight:700")
        side.addWidget(result_label)
        self.playback_results = QTableWidget(0, 3)
        self.playback_results.setHorizontalHeaderLabels(["Início", "Fim", "Tipo"])
        self.playback_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.playback_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.playback_results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.playback_results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playback_results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.playback_results.setShowGrid(False)
        self.playback_results.itemSelectionChanged.connect(self.playback_selection_changed)
        self.playback_results.itemDoubleClicked.connect(lambda _item: self.play_selected_recording())
        side.addWidget(self.playback_results, 1)
        self.playback_status = QLabel("Selecione gravador, canal e período de até 24 horas.")
        self.playback_status.setWordWrap(True)
        side.addWidget(self.playback_status)
        splitter.addWidget(sidebar)

        stage = QFrame()
        stage.setObjectName("VideoTile")
        player = QVBoxLayout(stage)
        player.setContentsMargins(12, 12, 12, 12)
        player.setSpacing(10)
        player_header = QHBoxLayout()
        video_title = QLabel("VISUALIZAÇÃO DA GRAVAÇÃO")
        video_title.setStyleSheet("color:#37c8e8;font-weight:700")
        player_header.addWidget(video_title)
        player_header.addStretch()
        self.playback_video_details = QLabel("Selecione um trecho à esquerda")
        self.playback_video_details.setStyleSheet("color:#a4bdc3")
        player_header.addWidget(self.playback_video_details)
        player.addLayout(player_header)

        self.playback_video_grid = QWidget()
        video_grid = QGridLayout(self.playback_video_grid)
        self.playback_video_layout = video_grid
        self.playback_focus_index = None
        video_grid.setContentsMargins(0, 0, 0, 0)
        video_grid.setSpacing(5)
        self.playback_screens = []
        for i in range(4):
            screen = PlaybackScreen(i, "Selecione um trecho à esquerda para reproduzir" if i == 0 else "")
            screen.doubleClicked.connect(self.toggle_playback_focus)
            screen.setToolTip("Dois cliques: ampliar câmera / voltar ao mosaico")
            screen.setAlignment(Qt.AlignCenter)
            screen.setMinimumHeight(135)
            screen.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            screen.setStyleSheet("background:#0b1722;color:#a4bdc3;border:1px solid #2a4452;border-radius:8px")
            video_grid.addWidget(screen, i // 2, i % 2)
            self.playback_screens.append(screen)
            if i:
                screen.hide()
        self.playback_screen = self.playback_screens[0]
        self.playback_video_grid.setMinimumHeight(280)
        player.addWidget(self.playback_video_grid, 1)

        timeline_label = QLabel("GRAVAÇÕES NO PERÍODO")
        timeline_label.setStyleSheet("color:#37c8e8;font-weight:700")
        player.addWidget(timeline_label)
        self.playback_timeline = RecordingTimeline()
        self.playback_timeline.timeHovered.connect(self.playback_time_hovered)
        self.playback_timeline.timeChosen.connect(self.playback_time_chosen)
        player.addWidget(self.playback_timeline)
        self.playback_hover_clock = QLabel("Passe o cursor sobre a linha do tempo para ver o horário")
        self.playback_hover_clock.setStyleSheet("color:#d7c99d")
        player.addWidget(self.playback_hover_clock)
        clip_label = QLabel("POSIÇÃO NO TRECHO")
        clip_label.setStyleSheet("color:#37c8e8;font-weight:700")
        player.addWidget(clip_label)
        timeline = QHBoxLayout()
        self.playback_elapsed = QLabel("00:00:00")
        timeline.addWidget(self.playback_elapsed)
        self.playback_seek = PlaybackSeekSlider(Qt.Horizontal)
        self.playback_seek.setEnabled(False)
        self.playback_seek.hoverSeconds.connect(self.playback_clip_hovered)
        self.playback_seek.sliderMoved.connect(self.playback_clip_hovered)
        self.playback_seek.sliderReleased.connect(self.seek_playback_stream)
        timeline.addWidget(self.playback_seek, 1)
        self.playback_duration = QLabel("00:00:00")
        timeline.addWidget(self.playback_duration)
        player.addLayout(timeline)
        controls = QHBoxLayout()
        self.playback_play_btn = QToolButton()
        self.playback_play_btn.setObjectName("PlaybackPlayAction")
        self.playback_play_btn.setIcon(self._tinted_icon(QStyle.StandardPixmap.SP_MediaPlay, "#37c8e8"))
        self.playback_play_btn.setIconSize(QSize(20, 20))
        self.playback_play_btn.setToolTip("Reproduzir o trecho selecionado")
        self.playback_play_btn.setAccessibleName("Reproduzir gravação")
        self.playback_play_btn.setEnabled(False)
        self.playback_play_btn.clicked.connect(lambda _checked=False: self.play_selected_recording())
        controls.addWidget(self.playback_play_btn)
        self.playback_stop_btn = QToolButton()
        self.playback_stop_btn.setObjectName("PlaybackStopAction")
        self.playback_stop_btn.setIcon(self._tinted_icon(QStyle.StandardPixmap.SP_MediaStop, "#f2a4a4"))
        self.playback_stop_btn.setIconSize(QSize(20, 20))
        self.playback_stop_btn.setToolTip("Parar reprodução")
        self.playback_stop_btn.setAccessibleName("Parar reprodução")
        self.playback_stop_btn.setEnabled(False)
        self.playback_stop_btn.clicked.connect(self.stop_playback_stream)
        controls.addWidget(self.playback_stop_btn)
        controls.addSpacing(8)
        for label, seconds in (("5 min", -300), ("30 s", -30), ("30 s", 30), ("5 min", 300)):
            button = QToolButton()
            button.setObjectName("PlaybackSkipAction")
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            pixmap = QStyle.StandardPixmap.SP_MediaSeekBackward if seconds < 0 else QStyle.StandardPixmap.SP_MediaSeekForward
            button.setIcon(self._tinted_icon(pixmap, "#c1e7ff"))
            button.setIconSize(QSize(16, 16))
            direction = "Voltar" if seconds < 0 else "Avançar"
            button.setToolTip(f"{direction} {label} na gravação")
            button.setAccessibleName(f"{direction} {label}")
            button.clicked.connect(lambda _checked=False, amount=seconds: self.skip_playback(amount))
            controls.addWidget(button)
        controls.addSpacing(8)
        speed_label = QLabel("Velocidade")
        speed_label.setStyleSheet("color:#a4bdc3")
        controls.addWidget(speed_label)
        self.playback_speed_combo = QComboBox()
        for label, value in (("0,5×", 0.5), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0),
                             ("8×", 8.0)):
            self.playback_speed_combo.addItem(label, value)
        self.playback_speed_combo.setCurrentIndex(1)
        self.playback_speed_combo.currentIndexChanged.connect(self.change_playback_speed)
        controls.addWidget(self.playback_speed_combo)
        controls.addStretch()
        self.playback_export_btn = QPushButton("Baixar MP4")
        self.playback_export_btn.setObjectName("PlaybackExport")
        self.playback_export_btn.setIcon(self._tinted_icon(QStyle.StandardPixmap.SP_DialogSaveButton, "#f2d590"))
        self.playback_export_btn.setToolTip("Salvar o trecho selecionado em MP4")
        self.playback_export_btn.setEnabled(False)
        self.playback_export_btn.clicked.connect(self.export_selected_recording)
        controls.addWidget(self.playback_export_btn)
        player.addLayout(controls)
        audio_row = QHBoxLayout()
        self.playback_listen_check = QCheckBox("Ouvir áudio")
        self.playback_listen_check.setToolTip("Escuta desligada por padrão; usa apenas o áudio gravado neste trecho")
        self.playback_listen_check.toggled.connect(self.toggle_playback_audio)
        audio_row.addWidget(self.playback_listen_check)
        self.playback_audio_source = QComboBox()
        self.playback_audio_source.setToolTip("No mosaico, escolha uma única câmera para ouvir")
        self.playback_audio_source.currentIndexChanged.connect(self.change_playback_audio_source)
        self.playback_audio_source.hide()
        audio_row.addWidget(self.playback_audio_source)
        self.playback_audio_muted = QCheckBox("Mudo")
        self.playback_audio_muted.toggled.connect(self.toggle_playback_audio)
        audio_row.addWidget(self.playback_audio_muted)
        audio_row.addWidget(QLabel("Volume"))
        self.playback_audio_volume = QSlider(Qt.Horizontal)
        self.playback_audio_volume.setRange(0, 100)
        self.playback_audio_volume.setValue(75)
        self.playback_audio_volume.setMaximumWidth(170)
        self.playback_audio_volume.valueChanged.connect(self.change_playback_audio_volume)
        self.playback_audio_volume.sliderReleased.connect(self.commit_playback_audio_volume)
        audio_row.addWidget(self.playback_audio_volume)
        self.playback_audio_status = QLabel("Áudio desligado")
        self.playback_audio_status.setStyleSheet("color:#a4bdc3")
        audio_row.addWidget(self.playback_audio_status, 1)
        self.playback_export_quality_label = QLabel("MP4:")
        audio_row.addWidget(self.playback_export_quality_label)
        self.playback_export_quality = QComboBox()
        self.playback_export_quality.addItem("Original", "original")
        self.playback_export_quality.addItem("Compacto", "compact")
        self.playback_export_quality.setToolTip(
            "Original preserva o vídeo do DVR e exige menos processamento.\n"
            "Compacto: até 720p e 15 FPS; arquivo menor, com conversão.\n"
            "A estimativa aparece na janela de salvar; o tamanho pode variar.")
        audio_row.addWidget(self.playback_export_quality)
        self.playback_export_silent = QCheckBox("MP4 sem áudio")
        self.playback_export_silent.setToolTip("Remove a faixa de áudio apenas do arquivo exportado")
        audio_row.addWidget(self.playback_export_silent)
        player.addLayout(audio_row)
        trim_row = QHBoxLayout()
        self.playback_mark_in_btn = QPushButton("Marcar início")
        self.playback_mark_in_btn.setObjectName("PlaybackMarkIn")
        self.playback_mark_in_btn.setIcon(self._scissors_icon("#bbf5d0"))
        self.playback_mark_in_btn.setToolTip("Início do trecho a exportar")
        self.playback_mark_in_btn.clicked.connect(self.mark_playback_in)
        trim_row.addWidget(self.playback_mark_in_btn)
        self.playback_mark_out_btn = QPushButton("Marcar fim")
        self.playback_mark_out_btn.setObjectName("PlaybackMarkOut")
        self.playback_mark_out_btn.setIcon(self._scissors_icon("#c1e7ff"))
        self.playback_mark_out_btn.setToolTip("Fim do trecho a exportar")
        self.playback_mark_out_btn.clicked.connect(self.mark_playback_out)
        trim_row.addWidget(self.playback_mark_out_btn)
        self.playback_trim_label = QLabel("Corte: trecho completo")
        trim_row.addWidget(self.playback_trim_label, 1)
        player.addLayout(trim_row)
        self.playback_diagnostic = QLabel("")
        self.playback_diagnostic.setWordWrap(True)
        self.playback_diagnostic.setStyleSheet("color:#d4aa75")
        player.addWidget(self.playback_diagnostic)
        splitter.addWidget(stage)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 1050])
        self.playback_poll_timer = QTimer(self)
        self.playback_poll_timer.setInterval(100)
        self.playback_poll_timer.timeout.connect(lambda: self._ui_metrics.run("playback", self.poll_playback_stream) if hasattr(self,"_ui_metrics") else self.poll_playback_stream())
        self.playback_poll_timer.start()
        from .playback_layout import compact_playback
        compact_playback(self, layout, splitter, sidebar, side, stage, player, timeline_label, clip_label, trim_row)
        self.playback_day_search_timer = QTimer(self)
        self.playback_day_search_timer.setSingleShot(True)
        self.playback_day_search_timer.setInterval(250)
        from .playback_layout import run_day_search
        self.playback_day_search_timer.timeout.connect(lambda: run_day_search(self))
        from .playback_layout import queue_day_search, sync_day
        self.playback_start.dateChanged.connect(lambda day: sync_day(self, day))
        self.playback_device_combo.currentIndexChanged.connect(lambda *_: queue_day_search(self))
        self.playback_channel_combo.currentIndexChanged.connect(lambda *_: queue_day_search(self))
        self.pages.addWidget(page)

    def refresh_playback_access(self, *_args):
        if not hasattr(self, "playback_device_combo"):
            return
        combo = self.playback_device_combo
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for device in self.db.list_devices(self.current_site_id):
            if self.db.list_recorder_channels(device["id"]):
                combo.addItem(device_visual_name(device), int(device["id"]))
        index = combo.findData(previous)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self.refresh_playback_channels()

    def refresh_playback_channels(self, *_args):
        if not hasattr(self, "playback_channel_combo"):
            return
        combo = self.playback_device_combo
        device_id = combo.currentData()
        self.playback_web_button.setEnabled(bool(device_id is not None and self._device_web_services(device_id)))
        if (getattr(self, "_playback_loaded_device_id", None) == device_id
                and self.playback_channel_combo.count()):
            return
        self._playback_loaded_device_id = device_id
        self.clear_playback_results()
        device = self.db.get_device(combo.currentData()) if combo.currentData() is not None else None
        self.playback_channel_combo.blockSignals(True)
        self.playback_channel_list.blockSignals(True)
        self.playback_channel_combo.clear()
        self.playback_channel_list.clear()
        if device:
            for channel in self.db.list_recorder_channels(int(device["id"])):
                number = int(channel["channel_no"])
                label = self.db.channel_display_name(channel)
                self.playback_channel_combo.addItem(label, number)
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, number)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if self.playback_channel_list.count() == 0 else Qt.Unchecked)
                self.playback_channel_list.addItem(item)
        self.playback_channel_combo.blockSignals(False)
        self.playback_channel_list.blockSignals(False)
        web_url = QUrl((device["web_url"] or "").strip()) if device else QUrl()
        web_ok = web_url.scheme().lower() in ("http", "https") and bool(web_url.host()) and not web_url.userName() and not web_url.password()
        identity = " ".join(str(device[key] or "") for key in ("manufacturer", "provider")) if device else ""
        supported = "intelbras" in identity.lower() or uses_hikvision_recordings(device)
        cloud_ok=bool(device is not None and is_cloud_device(device))
        self.playback_access_note.setText(
            "SDK Hikvision local • Main/pesquisa validados; reprodução em validação • somente 1×." if device is not None and hik_sdk_settings(device)["enabled"] else
            "Busca Cloud pelo SDK • não exige interface Web." if cloud_ok else
            "Busca interna disponível para gravadores Intelbras e Hikvision compatíveis."
            if web_ok else "Nenhum gravador com interface Web disponível neste Site. Confira o cadastro e o acesso de rede."
        )
        self.playback_search_btn.setEnabled((cloud_ok or (device is not None and hik_sdk_settings(device)["enabled"]) or (web_ok and supported)) and self.playback_channel_combo.count() > 0)
        speed = getattr(self, "playback_speed_combo", None)
        if speed is not None:
            from .hik_sdk import settings as hik_settings
            sdk_active=bool(device is not None and hik_settings(device)["enabled"])
            hik_active=bool(device is not None and uses_hikvision_recordings(device))
            if hik_active and not sdk_active:speed.setCurrentIndex(max(0,speed.findData(1.0)))
            speed.setEnabled(not hik_active or sdk_active)
            speed.setToolTip('Hikvision RTSP: 1×. Aceleração 2×/4×/8× exige SDK local e validação do avanço real.' if hik_active else 'Velocidade solicitada; confirme o avanço medido.')

    def toggle_playback_multi(self, checked):
        self.set_playback_focus(None)
        self.playback_channel_combo.setVisible(not checked)
        self.playback_channel_list.setVisible(checked)
        self.clear_playback_results()
        self.playback_export_btn.setEnabled(False)
        self.playback_mark_in_btn.setEnabled(not checked)
        self.playback_mark_out_btn.setEnabled(not checked)
        self.playback_audio_source.setVisible(checked)
        self.playback_export_silent.setVisible(not checked)
        self.playback_export_quality.setVisible(not checked)
        self.playback_export_quality_label.setVisible(not checked)

    def selected_playback_channels(self):
        if not self.playback_multi_check.isChecked():
            value = self.playback_channel_combo.currentData()
            return (int(value),) if value is not None else ()
        return tuple(int(self.playback_channel_list.item(i).data(Qt.UserRole))
                     for i in range(self.playback_channel_list.count())
                     if self.playback_channel_list.item(i).checkState() == Qt.Checked)

    def playback_channel_checked(self, item):
        if item.checkState() == Qt.Checked and len(self.selected_playback_channels()) > 4:
            self.playback_channel_list.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.playback_channel_list.blockSignals(False)
            self.playback_status.setText("Selecione no máximo quatro câmeras na mesma linha do tempo.")
            return
        self.clear_playback_results()

    def clear_playback_results(self, *_args):
        if not hasattr(self, "playback_results"):
            return
        self.stop_playback_stream()
        self.playback_clip_bounds = None
        self.playback_results.setRowCount(0)
        self.playback_play_btn.setEnabled(False)
        self.playback_export_btn.setEnabled(False)
        self.playback_timeline.set_period(None, None)
        self.playback_seek.setEnabled(False)
        self.playback_seek.setValue(0)
        self.playback_trim_start = self.playback_trim_end = None
        self.playback_trim_label.setText("Corte: trecho completo")
        self.playback_multi_recordings = ()

    def playback_selection_changed(self):
        if self.playback_session is not None:
            self.stop_playback_stream()
        self.playback_clip_bounds = None
        self.playback_seek.setEnabled(False)
        selected = bool(self.playback_results.selectedItems())
        self.playback_play_btn.setEnabled(selected)
        self.playback_export_btn.setEnabled(selected and not self.playback_multi_check.isChecked()
                                            and self.playback_export_worker is None)
        self.playback_trim_start = self.playback_trim_end = None
        self.playback_trim_label.setText("Corte: trecho completo")

    def playback_time_hovered(self, point):
        self.playback_hover_clock.setText(f"Cursor: {point:%d/%m/%Y %H:%M:%S}")

    def playback_clip_hovered(self, seconds):
        if self.playback_clip_bounds:
            point = self.playback_clip_bounds[0] + timedelta(seconds=seconds)
            self.playback_hover_clock.setText(f"Cursor: {point:%d/%m/%Y %H:%M:%S}")
            QToolTip.showText(QCursor.pos(), point.strftime("%d/%m/%Y %H:%M:%S"), self.playback_seek)

    def change_playback_speed(self, *_args):
        if self.playback_session is not None and self.playback_clip_bounds:
            self.seek_playback_stream(force_reopen=True)

    def stop_playback_audio(self):
        session = self.playback_audio_session
        self.playback_audio_session = None
        if session is not None:
            session.stop()

    def toggle_playback_audio(self, *_args):
        self.stop_playback_audio()
        if not authorize(self,'recorded_audio',notify=False):
            self.playback_audio_status.setText('Áudio gravado restrito pelo administrador')
            return
        if (not self.playback_listen_check.isChecked() or self.playback_audio_muted.isChecked()
                or self.playback_audio_volume.value() == 0):
            self.playback_audio_status.setText("Áudio desligado" if not self.playback_listen_check.isChecked()
                                               else "Áudio mudo")
            return
        if getattr(self, 'playback_speed_combo', None) is not None and float(self.playback_speed_combo.currentData()) != 1:
            self.playback_audio_status.setText("Áudio pausado nesta velocidade; disponível em 1×")
            return
        route = self.playback_audio_route
        if route is None:
            self.playback_audio_status.setText("Abra uma gravação para ouvir")
            return
        url, credentials = route
        if str(url).startswith("hik-sdk:"):
            self.playback_audio_status.setText("Áudio pelo SDK Hikvision ainda não validado")
            return
        video = (self.playback_sessions.get(self.playback_audio_source.currentData())
                 if self.playback_multi_check.isChecked() else self.playback_session)
        if (video is not None and hasattr(video, '_playback_fanout')
                and video._playback_fanout is not None and video._playback_fanout.ready.is_set()):
            # A file header may already have passed. Restart at the current cursor
            # with audio subscribed before the SDK sends the new header.
            self.seek_playback_stream()
            return
        if video is not None and hasattr(video, 'create_recording_audio'):
            session = video.create_recording_audio(volume=self.playback_audio_volume.value())
        else:
            session = create_live_audio_session(url, credentials[0], credentials[1],
                                       volume=self.playback_audio_volume.value(), playback=True,
                                       playback_speed=float(self.playback_speed_combo.currentData()))
        if not session.player_available:
            self.playback_audio_status.setText("Saída de áudio local indisponível")
            return
        self.playback_audio_session = session
        self.playback_audio_status.setText("Procurando áudio gravado…")
        session.start()

    def change_playback_audio_volume(self, value):
        if value == 0:
            self.stop_playback_audio()
            self.playback_audio_status.setText("Áudio mudo")
        elif self.playback_audio_session is not None:
            self.playback_audio_session.set_volume(value)
        elif self.playback_listen_check.isChecked() and not self.playback_audio_muted.isChecked():
            self.toggle_playback_audio()

    def commit_playback_audio_volume(self):
        session = self.playback_audio_session
        if session is not None and not session.dynamic_volume_active:
            self.toggle_playback_audio()

    def change_playback_audio_source(self, *_args):
        if (not self.playback_multi_check.isChecked() or not self.playback_audio_candidates
                or not self.playback_clip_bounds):
            return
        channel = self.playback_audio_source.currentData()
        candidate = self.playback_audio_candidates.get(channel)
        if candidate is None:
            self.playback_audio_route = None
            self.stop_playback_audio()
            self.playback_audio_status.setText("Sem gravação neste canal no horário atual")
            return
        host, port, end, credentials, recording = candidate
        point = self.playback_clip_bounds[0] + timedelta(seconds=self.playback_seek.value())
        if point >= end:
            self.playback_audio_route = None
            self.stop_playback_audio()
            self.playback_audio_status.setText("Trecho de áudio encerrado")
            return
        self.playback_audio_route = (self.recording_route(recording, host, int(channel), point, end, port), credentials)
        self.toggle_playback_audio()

    def playback_time_chosen(self, point):
        if self.playback_multi_check.isChecked():
            self.playback_multi_at(point)
            return
        for row in range(self.playback_results.rowCount()):
            item = self.playback_results.item(row, 0)
            recording = item.data(Qt.UserRole) if item else None
            if recording and recording.start <= point.strftime("%Y-%m-%d %H:%M:%S") < recording.end:
                self.playback_results.blockSignals(True)
                try:
                    self.playback_results.selectRow(row)
                finally:
                    self.playback_results.blockSignals(False)
                self.play_selected_recording(at=point)
                return
        self.playback_diagnostic.setText(f"Sem gravação no horário {point:%H:%M:%S}.")

    def _playback_mark_point(self):
        if not self.playback_clip_bounds:
            return None
        return self.playback_clip_bounds[0] + timedelta(seconds=self.playback_seek.value())

    def mark_playback_in(self):
        point = self._playback_mark_point()
        if point:
            self.playback_trim_start = point
            self.update_playback_trim_label()

    def mark_playback_out(self):
        point = self._playback_mark_point()
        if point:
            self.playback_trim_end = point
            self.update_playback_trim_label()

    def update_playback_trim_label(self):
        if not self.playback_clip_bounds:
            return
        start = self.playback_trim_start or self.playback_clip_bounds[0]
        end = self.playback_trim_end or self.playback_clip_bounds[1]
        valid = end > start
        self.playback_trim_label.setText(
            f"Corte: {start:%H:%M:%S} → {end:%H:%M:%S}" if valid else
            "Corte inválido: o fim deve ser posterior ao início")
        self.playback_export_btn.setEnabled(valid and self.playback_export_worker is None)

    @staticmethod
    def playback_clock(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"

    def selected_playback_clip(self):
        row = self.playback_results.currentRow()
        item = self.playback_results.item(row, 0) if row >= 0 else None
        recording = item.data(Qt.UserRole) if item else None
        device_id = self.playback_device_combo.currentData()
        device = self.db.get_device(device_id) if device_id is not None else None
        credentials = self._credentials_for_device(int(device_id)) if device else None
        if not recording or not device or not credentials:
            raise ValueError("Selecione um trecho e confira a credencial do gravador")
        clip_start = datetime.strptime(recording.start, "%Y-%m-%d %H:%M:%S")
        clip_end = datetime.strptime(recording.end, "%Y-%m-%d %H:%M:%S")
        start = max(clip_start, self.playback_start.dateTime().toPython())
        end = min(clip_end, self.playback_end.dateTime().toPython())
        channel_no = int(recording.channel if self.playback_multi_check.isChecked()
                         else self.playback_channel_combo.currentData())
        target, rtsp_port = self.playback_channel_endpoint(int(device_id), channel_no)
        return target, rtsp_port, channel_no, start, end, credentials

    def playback_channel_endpoint(self, device_id, channel_no):
        device = self.db.get_device(device_id)
        if not device:
            raise ValueError("Gravador indisponível")
        channel_rows = self.db.list_recorder_channels(int(device_id))
        selected = next((ch for ch in channel_rows if int(ch["channel_no"]) == channel_no), None)
        stream = (selected["main_rtsp_url"] or selected["rtsp_url"]) if selected else ""
        parsed_stream = urlparse(stream)
        if is_cloud_device(device):
            return stream,parsed_stream.port
        from .hik_sdk import settings as hik_settings
        target = device["web_url"] or ("http://"+device["ip"] if hik_settings(device)["enabled"] else "")
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        rtsp_port = int(metadata.get("recorder_rtsp_port") or 554)
        if parsed_stream.scheme in ("rtsp", "rtsps") and parsed_stream.hostname:
            host = parsed_stream.hostname
            target = f"http://[{host}]" if ":" in host else f"http://{host}"
            rtsp_port = parsed_stream.port or 554
        return target, rtsp_port

    def recording_route(self, recording, host, channel, start, end, port, *, native=True):
        route=recording.playback_uri if recording is not None else host
        if urlparse(str(route)).scheme in {'intelbras-cloud','intelbras-wine'}:
            from .intelbras_cloud_recordings import playback_route
            return playback_route(route,start,end)
        if recording is not None and str(recording.playback_uri).startswith("hik-sdk:"):
            from .hik_sdk import parse_route,route
            options=parse_route(recording.playback_uri)
            return route(options["host"],options["port"],options["channel"],start,end)
        if recording is not None and recording.playback_uri:
            return hikvision_playback_url(recording, host, start, end, port=port)
        if native and getattr(self,'playback_speed_combo',None) is not None and float(self.playback_speed_combo.currentData())!=1.0:
            device_id=self.playback_device_combo.currentData()
            device=self.db.get_device(device_id) if device_id is not None else None
            if device is not None and 'intelbras' in str(device['provider']).lower():
                from .intelbras_cloud import default_sdk_dir
                from .intelbras_local_playback import local_playback_route
                if not (default_sdk_dir()/'libdhnetsdk.so').is_file():
                    raise ValueError('Aceleração Intelbras exige NetSDK Linux instalado. Use 1× ou importe o SDK.')
                metadata=json.loads(device['metadata_json'] or '{}')
                return local_playback_route(urlparse(host).hostname,int(metadata.get('netsdk_port') or 37777),channel,start,end,device['serial'] or '')
        return playback_rtsp_url(host, channel, start, end, port=port)

    def selected_recording_row(self):
        row = self.playback_results.currentRow()
        item = self.playback_results.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    @requires_permission('playback')
    def search_playback_recordings(self):
        device_id = self.playback_device_combo.currentData()
        channels = self.selected_playback_channels()
        device = self.db.get_device(device_id) if device_id is not None else None
        if self.playback_search_worker is not None:
            return
        from .playback_layout import set_day_busy
        set_day_busy(self,False)
        if not device:
            return
        if not channels or len(channels) > 4:
            self.playback_status.setText("Selecione de uma a quatro câmeras para a busca.")
            return
        credentials = self._credentials_for_device(int(device_id))
        if credentials is None:
            self.playback_status.setText("Informe a credencial do gravador em Equipamentos → Canais antes da busca.")
            return
        start = self.playback_start.dateTime().toPython()
        end = self.playback_end.dateTime().toPython()
        if end <= start or (end - start).total_seconds() > 86400:
            self.playback_status.setText("Selecione um período válido de até 24 horas.")
            return
        self.playback_search_btn.setEnabled(False)
        self.clear_playback_results()
        self.playback_status.setText("Consultando os arquivos gravados…")
        self.playback_diagnostic.clear()
        hikvision = uses_hikvision_recordings(device)
        from .hik_sdk import settings as hik_settings
        if hikvision and hik_settings(device)["enabled"]:
            from .hik_sdk import search_recordings as sdk_search
            worker=Worker(sdk_search,dict(device),credentials[0],credentials[1],channels,start,end)
            self.playback_status.setText("Consultando gravações pelo SDK Hikvision local • horário do DVR…")
        elif is_cloud_device(device):
            from .intelbras_cloud_recordings import search_cloud_recordings
            cloud_route,_port=self.playback_channel_endpoint(int(device_id),channels[0])
            worker=Worker(search_cloud_recordings,cloud_route,credentials[0],credentials[1],channels,start,end)
            self.playback_status.setText("Consultando gravações pelo Cloud • horário local do DVR…")
        elif len(channels) == 1:
            worker = Worker(search_hikvision_recordings if hikvision else search_recordings,
                            device["web_url"], credentials[0], credentials[1], channels[0], start, end)
        else:
            worker = Worker(search_hikvision_recordings_multi if hikvision else search_recordings_multi,
                            device["web_url"], credentials[0], credentials[1], channels, start, end)
        self.playback_search_worker = worker
        set_day_busy(self,True)
        worker.signals.result.connect(
            lambda result, did=int(device_id), ch=channels, begin=start, finish=end:
            self.playback_search_result(result, did, ch, begin, finish))
        from .playback_layout import day_search_error
        worker.signals.error.connect(lambda error: day_search_error(self, error))
        worker.signals.finished.connect(self.playback_search_finished)
        self.start_qt_worker(worker)

    def playback_search_result(self, result, device_id, channels, start, end):
        if (self.playback_device_combo.currentData() != device_id
                or self.selected_playback_channels() != channels
                or self.playback_start.dateTime().toPython() != start
                or self.playback_end.dateTime().toPython() != end):
            return
        self.playback_multi_recordings = result.recordings
        from .runtime_diagnostics import record_runtime
        for line in getattr(result,'diagnostics',()):record_runtime(self,'pesquisa',line)
        self.playback_results.setRowCount(len(result.recordings))
        self.playback_timeline.set_period(start, end, result.recordings,
                                          channels if self.playback_multi_check.isChecked() else ())
        self.playback_results.setHorizontalHeaderLabels(
            ["Canal / Início", "Fim", "Tipo"] if len(channels) > 1 else ["Início", "Fim", "Tipo"])
        for row, recording in enumerate(result.recordings):
            first = (f"CAM {recording.channel} • " if len(channels) > 1 else "") + recording.start[11:]
            for col, value in enumerate((first, recording.end[11:], recording.kind)):
                self.playback_results.setItem(row, col, QTableWidgetItem(str(value)))
            self.playback_results.item(row, 0).setData(Qt.UserRole, recording)
        suffix = " • limite da busca atingido; reduza o período" if result.truncated else ""
        if result.ignored:
            suffix += f" • {result.ignored} arquivo(s) fora do canal/período ignorado(s) pelo filtro local"
        if result.warnings:
            suffix += " • " + " | ".join(result.warnings)
        self.playback_status.setText(f"{len(result.recordings)} trecho(s) no período selecionado{suffix}.")

    @requires_permission('playback')
    def play_selected_recording(self, *, at=None):
        if self.playback_multi_check.isChecked():
            try:
                _host, _port, _channel, start, _end, _credentials = self.selected_playback_clip()
                self.playback_multi_at(at if isinstance(at, datetime) else start)
            except (ValueError, TypeError, RuntimeError):
                self.playback_status.setText("Selecione uma gravação válida.")
            return
        try:
            target, rtsp_port, channel_no, start, end, credentials = self.selected_playback_clip()
            offset = int((at - start).total_seconds()) if isinstance(at, datetime) and start < at < end else 0
            url = self.recording_route(self.selected_recording_row(), target, channel_no,
                                       start + timedelta(seconds=offset), end, rtsp_port)
        except (ValueError, TypeError, RuntimeError):
            self.playback_status.setText("Trecho inválido; refaça a busca de gravações.")
            return
        self.stop_playback_stream(preserve_focus=True)
        self.playback_clip_bounds = (start, end)
        self.playback_seek.setRange(0, max(1, int((end - start).total_seconds())))
        self.playback_seek.setValue(offset)
        self.playback_seek.setEnabled(True)
        self.playback_duration.setText(self.playback_clock((end - start).total_seconds()))
        self.playback_elapsed.setText(self.playback_clock(offset))
        self.playback_started_at = None
        self.playback_offset_seconds = offset
        self.playback_video_details.setText(f"{self.playback_channel_combo.currentText()} • {start:%d/%m/%Y %H:%M}–{end:%H:%M}")
        self.playback_diagnostic.clear()
        self.playback_screen.setText("Conectando à gravação…")
        self.playback_status.setText(f"Reproduzindo {start:%d/%m/%Y %H:%M} até {end:%H:%M} • {self.playback_channel_combo.currentText()}")
        self.playback_session = create_live_stream_session(
            url, credentials[0], credentials[1], fps=10, profile_name="Gravação",
            stop_after_initial_failures=3, playback=True,
            playback_speed=float(self.playback_speed_combo.currentData()),
        )
        self.playback_stop_btn.setEnabled(True)
        from .playback_layout import set_video_busy
        set_video_busy(self,True,start + timedelta(seconds=offset))
        self.playback_audio_route = (url, credentials)
        self.toggle_playback_audio()
        from .media_observation import transport_name
        from .runtime_diagnostics import record_runtime
        record_runtime(self,'reprodução','Acesso ativo: '+transport_name(url))
        if uses_hikvision_recordings(self.db.get_device(self.playback_device_combo.currentData())):
            self.playback_session.frame_width=1280;self.playback_session.frame_height=720
        self.playback_session.start()

    @requires_permission('playback')
    def playback_multi_at(self, point):
        channels = self.selected_playback_channels()
        available = {}
        for recording in self.playback_multi_recordings:
            if (recording.channel in channels and recording.channel not in available
                    and recording.start <= point.strftime("%Y-%m-%d %H:%M:%S") < recording.end):
                available[recording.channel] = recording
        if not available:
            self.playback_diagnostic.setText(f"Sem gravação nas câmeras selecionadas às {point:%H:%M:%S}.")
            return
        device_id = self.playback_device_combo.currentData()
        credentials = self._credentials_for_device(int(device_id)) if device_id is not None else None
        if not credentials:
            self.playback_diagnostic.setText("Credencial do gravador indisponível.")
            return
        self.stop_playback_stream(preserve_focus=True)
        active = []
        for channel in channels:
            if channel not in available:
                continue
            recording = available[channel]
            try:
                host, port = self.playback_channel_endpoint(int(device_id), channel)
                end = min(datetime.strptime(recording.end, "%Y-%m-%d %H:%M:%S"),
                          self.playback_end.dateTime().toPython())
                url = self.recording_route(recording, host, channel, point, end, port)
            except (ValueError, TypeError, RuntimeError):
                continue
            index = len(active)
            active.append(channel)
            screen = self.playback_screens[index]
            screen.show()
            screen.setPixmap(QPixmap())
            screen.setText(f"CAM {channel} • conectando às {point:%H:%M:%S}…")
            session = create_live_stream_session(
                url, credentials[0], credentials[1], fps=8, profile_name=f"CAM {channel}",
                stop_after_initial_failures=3, playback=True,
                playback_speed=float(self.playback_speed_combo.currentData()))
            self.playback_sessions[channel] = session
            self.playback_audio_candidates[channel] = (host, port, end, credentials, recording)
        self.playback_active_channels = tuple(active)
        if self.playback_focus_index is not None and self.playback_focus_index >= len(active):
            self.set_playback_focus(None)
        for screen in self.playback_screens[len(self.playback_active_channels):]:
            screen.hide()
        if self.playback_focus_index is not None:
            self.set_playback_focus(self.playback_focus_index)
        self.playback_session = next(iter(self.playback_sessions.values()), None)
        from .playback_layout import set_video_busy
        set_video_busy(self,bool(self.playback_sessions),point)
        self.playback_clip_bounds = (self.playback_start.dateTime().toPython(),
                                     self.playback_end.dateTime().toPython())
        self.playback_offset_seconds = int((point - self.playback_clip_bounds[0]).total_seconds())
        self.playback_started_at = None
        self.playback_seek.setRange(0, int((self.playback_clip_bounds[1] - self.playback_clip_bounds[0]).total_seconds()))
        self.playback_seek.setValue(self.playback_offset_seconds)
        self.playback_seek.setEnabled(True)
        self.playback_elapsed.setText(self.playback_clock(self.playback_offset_seconds))
        self.playback_duration.setText(self.playback_clock(self.playback_seek.maximum()))
        self.playback_video_details.setText(f"{len(self.playback_sessions)} câmera(s) • {point:%d/%m/%Y %H:%M:%S}")
        self.playback_stop_btn.setEnabled(bool(self.playback_sessions))
        self.playback_diagnostic.setText("Sincronização pelo horário solicitado; atraso de rede pode variar entre câmeras.")
        self.playback_audio_source.blockSignals(True)
        previous = self.playback_audio_source.currentData()
        self.playback_audio_source.clear()
        for channel in active:
            self.playback_audio_source.addItem(f"Ouvir CAM {channel}", channel)
        selected = self.playback_audio_source.findData(previous)
        self.playback_audio_source.setCurrentIndex(max(0, selected))
        self.playback_audio_source.blockSignals(False)
        self.change_playback_audio_source()
        for session in self.playback_sessions.values():
            session.start()

    def stop_playback_stream(self, *, preserve_focus=False):
        from .playback_layout import set_video_busy
        set_video_busy(self,False)
        self.stop_playback_audio()
        self.playback_audio_route = None
        self.playback_audio_candidates = {}
        if hasattr(self, "playback_audio_status"):
            self.playback_audio_status.setText("Áudio desligado")
        session = getattr(self, "playback_session", None)
        self.playback_session = None
        sessions = list(getattr(self, "playback_sessions", {}).values())
        self.playback_sessions = {}
        if session is not None and session not in sessions:
            sessions.append(session)
        for item in sessions:
            item.stop()
        if hasattr(self, "playback_stop_btn"):
            if not preserve_focus:
                self.set_playback_focus(None)
            self.playback_stop_btn.setEnabled(False)
            for index, screen in enumerate(self.playback_screens):
                screen.setPixmap(QPixmap())
                screen.setText("Selecione um trecho da lista e clique em Reproduzir" if index == 0 else "")
                if index:
                    screen.hide()
                screen.reset_zoom()
            self.playback_seek.setEnabled(self.playback_clip_bounds is not None)

    def toggle_playback_focus(self, index):
        if self.playback_multi_check.isChecked() and index >= len(self.playback_active_channels):
            return
        if index and not self.playback_multi_check.isChecked():
            return
        self.set_playback_focus(None if self.playback_focus_index == index else index)

    def set_playback_focus(self, index):
        if not hasattr(self, "playback_screens"):
            return
        self.playback_focus_index = index
        for i, screen in enumerate(self.playback_screens):
            if index is None:
                screen.setVisible(i == 0 if not self.playback_multi_check.isChecked()
                                  else i < len(self.playback_active_channels))
            else:
                screen.setVisible(i == index)
        visible = [i for i in range(4) if (i == index if index is not None else
                   (i < len(self.playback_active_channels) if self.playback_multi_check.isChecked() else i == 0))]
        for i, screen in enumerate(self.playback_screens):
            screen.setProperty('dense_preview', len(visible) > 1)
        for row in range(2):
            self.playback_video_layout.setRowStretch(row, int(any(i // 2 == row for i in visible)))
            self.playback_video_layout.setColumnStretch(row, int(any(i % 2 == row for i in visible)))

    def skip_playback(self, seconds):
        if not self.playback_clip_bounds or not self.playback_seek.isEnabled():
            self.playback_status.setText("Abra uma gravação antes de saltar no tempo.")
            return
        position = max(0, min(self.playback_seek.maximum() - 1, self.playback_seek.value() + seconds))
        if position == self.playback_seek.value():
            return
        self.playback_seek.setValue(position)
        self.playback_elapsed.setText(self.playback_clock(position))
        self.seek_playback_stream()

    @requires_permission('playback')
    def seek_playback_stream(self, *, force_reopen=False):
        if not self.playback_clip_bounds:
            return
        start, end = self.playback_clip_bounds
        target = start + timedelta(seconds=self.playback_seek.value())
        if target >= end:
            return
        if self.playback_multi_check.isChecked():
            self.playback_multi_at(target)
            return
        try:
            host, port, channel, _start, _end, credentials = self.selected_playback_clip()
            url = self.recording_route(self.selected_recording_row(), host, channel, target, end, port)
        except (ValueError, TypeError, RuntimeError):
            return
        session=self.playback_session
        if (not force_reopen and session is not None and hasattr(session,'request_playback_seek')
                and not self.playback_listen_check.isChecked()):
            accepted=session.request_playback_seek(url,float(self.playback_speed_combo.currentData()))
            if accepted is None:return  # Previous jump is still preparing its image.
            if accepted:
                self.playback_started_at=None
                self.playback_offset_seconds=int((target-start).total_seconds())
                self.playback_audio_route=(url,credentials)
                self.playback_seek.setEnabled(True)
                from .playback_layout import set_video_busy
                set_video_busy(self,True,target)
                return
        self.stop_playback_stream(preserve_focus=True)
        self.playback_clip_bounds = (start, end)
        self.playback_started_at = None
        self.playback_offset_seconds = int((target - start).total_seconds())
        self.playback_seek.setEnabled(True)
        self.playback_screen.setText("Buscando posição na gravação…")
        self.playback_session = create_live_stream_session(
            url, credentials[0], credentials[1], fps=10, profile_name="Gravação",
            stop_after_initial_failures=3, playback=True,
            playback_speed=float(self.playback_speed_combo.currentData()))
        self.playback_stop_btn.setEnabled(True)
        from .playback_layout import set_video_busy
        set_video_busy(self,True,target)
        self.playback_audio_route = (url, credentials)
        self.toggle_playback_audio()
        from .media_observation import transport_name
        from .runtime_diagnostics import record_runtime
        record_runtime(self,'reprodução','Acesso ativo: '+transport_name(url))
        if uses_hikvision_recordings(self.db.get_device(self.playback_device_combo.currentData())):
            self.playback_session.frame_width=1280;self.playback_session.frame_height=720
        self.playback_session.start()

    def poll_playback_stream(self):
        from .playback_layout import poll_video_busy
        poll_video_busy(self)
        audio = self.playback_audio_session
        if audio is not None:
            status = audio.latest_status()
            from .runtime_diagnostics import record_runtime
            if status:
                self.playback_audio_status.setText(status)
                record_runtime(self, "áudio gravado", status)
            for line in audio.drain_diagnostics():
                record_runtime(self, "áudio gravado", line)
        session = self.playback_session
        if session is None:
            return
        frames = {}
        if self.playback_multi_check.isChecked() and self.playback_sessions:
            for index, channel in enumerate(self.playback_active_channels):
                item = self.playback_sessions.get(channel)
                if item is None:
                    continue
                packet = item.latest_frame()
                if packet is not None:
                    frames[channel] = packet
                    image = QImage(packet.pixels, packet.width, packet.height,
                                   packet.width * 3, QImage.Format_RGB888).copy()
                    screen = self.playback_screens[index]
                    screen.set_frame(image)
                status = item.latest_status()
                if status and not item.ever_had_frame:
                    self.playback_screens[index].setText(f"CAM {channel} • {status}")
                diagnostics = item.drain_diagnostics()
                from .runtime_diagnostics import record_runtime
                for line in diagnostics: record_runtime(self, f"reprodução CAM {channel}", line)
                if diagnostics and not item.ever_had_frame:
                    self.playback_diagnostic.setText(f"CAM {channel} • {diagnostics[-1]}")
            frame = frames.get(self.playback_active_channels[0]) if self.playback_active_channels else None
        else:
            frame = session.latest_frame()
        if frame is not None and self.playback_started_at is None:
            self.playback_started_at = time.monotonic()
        if self.playback_started_at is not None and not self.playback_seek.isSliderDown():
            position = getattr(session, 'playback_position_seconds', None)
            if position is None and not hasattr(session, 'playback_position_seconds'):
                position = (time.monotonic() - self.playback_started_at) * float(self.playback_speed_combo.currentData())
            if position is not None:
                elapsed = min(self.playback_seek.maximum(), self.playback_offset_seconds + int(position))
                self.playback_seek.setValue(elapsed)
                self.playback_elapsed.setText(self.playback_clock(elapsed))
            requested = float(self.playback_speed_combo.currentData())
            if requested != 1 and session.current_state == 'playing':
                rate = getattr(session, 'measured_playback_speed', None)
                measured = f"medida {rate:.2f}×" if rate is not None else "medindo avanço da mídia…"
                self.playback_diagnostic.setText(f"Solicitada {requested:g}× • {measured}")
        if frame is not None and not self.playback_multi_check.isChecked():
            from .media_observation import session_label
            self.playback_video_details.setText(self.playback_channel_combo.currentText()+' · '+session_label(session))
            image = QImage(frame.pixels, frame.width, frame.height, frame.width * 3, QImage.Format_RGB888).copy()
            self.playback_screen.set_frame(image)
        if self.playback_multi_check.isChecked():
            return
        status = session.latest_status()
        if status and frame is None and not session.ever_had_frame:
            self.playback_screen.setText(status)
            self.playback_diagnostic.setText(status)
        elif status and status.startswith("Fim do trecho"):
            self.playback_diagnostic.setText(status)
        diagnostics = session.drain_diagnostics()
        from .runtime_diagnostics import record_runtime
        for line in diagnostics: record_runtime(self, "reprodução", line)
        if diagnostics and not session.ever_had_frame:
            self.playback_diagnostic.setText(diagnostics[-1])
        if frame is not None and float(self.playback_speed_combo.currentData()) == 1:
            self.playback_diagnostic.clear()

    @requires_permission('export')
    def export_selected_recording(self):
        device_id=self.playback_device_combo.currentData()
        device=self.db.get_device(device_id) if device_id is not None else None
        if self.playback_export_worker is not None:
            return
        try:
            host, port, channel, start, end, credentials = self.selected_playback_clip()
            from .recording_export import export_bounds
            start, end = export_bounds(start, end, self.playback_trim_start, self.playback_trim_end)
            url = self.recording_route(self.selected_recording_row(), host, channel, start, end, port,native=False)
        except (ValueError, TypeError, RuntimeError):
            self.playback_diagnostic.setText("Selecione uma gravação válida para exportar.")
            return
        quality = self.playback_export_quality.currentData()
        include_audio = not self.playback_export_silent.isChecked() and authorize(self,'export_audio',notify=False)
        from .recording_export_profiles import export_note
        note = export_note(quality, (end-start).total_seconds(), include_audio)
        suffix = ("_compacto" if quality == "compact" else "") + ("_sem_audio" if not include_audio else "")
        default_name = f"Sentinel_CAM{channel}_{start:%Y%m%d_%H%M%S}{suffix}.mp4"
        destination, _ = QFileDialog.getSaveFileName(self, "Salvar MP4 • " + note, default_name, "Vídeo MP4 (*.mp4)")
        if not destination:
            return
        if self.playback_session is not None or self.playback_sessions:
            self.stop_playback_stream(preserve_focus=True)
            self.playback_status.setText("Reprodução parada durante a exportação; pressione Reproduzir para voltar.")
        self.playback_export_cancel = threading.Event()
        worker = Worker(export_mp4, url, credentials[0], credentials[1], destination,
                        int((end - start).total_seconds()), cancel=self.playback_export_cancel,
                        include_audio=include_audio, quality=quality,
                        with_progress=True)
        worker.kwargs['diagnostics'] = worker.signals.diagnostic.emit
        worker.signals.diagnostic.connect(self.playback_export_diagnostic)
        self.playback_export_worker = worker
        self.playback_export_btn.setEnabled(False)
        self.playback_export_dialog = QProgressDialog("Preparando exportação…", "Cancelar", 0, 0, self)
        self.playback_export_dialog.setWindowTitle("Exportar MP4")
        self.playback_export_dialog.setMinimumDuration(0)
        self.playback_export_dialog.canceled.connect(self.playback_export_cancel.set)
        worker.signals.progress.connect(self.playback_export_progress)
        worker.signals.result.connect(self.playback_export_success)
        worker.signals.error.connect(self.playback_export_error)
        worker.signals.finished.connect(self.playback_export_finished)
        self.playback_export_dialog.show()
        self.start_qt_worker(worker)

    def playback_export_success(self,path):
        from pathlib import Path
        target=Path(path)
        if not target.is_file() or not target.stat().st_size:
            self.playback_export_error('O processo encerrou sem arquivo final no destino.');return
        self.playback_status.setText(f'MP4 salvo em {target}')
        self.playback_export_diagnostic(f'MP4 salvo • {target.stat().st_size} bytes')
        QMessageBox.information(self,'Vídeo exportado',f'Arquivo salvo:\n{target}\n\nTamanho: {target.stat().st_size/1_000_000:.1f} MB')

    def playback_export_progress(self, message):
        import re
        dialog = getattr(self, 'playback_export_dialog', None)
        if dialog is None:
            return
        dialog.setLabelText(message)
        fraction = re.search(r'(\d+)%', message)
        if fraction:
            dialog.setRange(0, 100)
            dialog.setValue(min(99, int(fraction[1])))

    def playback_export_diagnostic(self, message):
        from .runtime_diagnostics import record_runtime
        record_runtime(self, "exportação", message)

    def playback_export_error(self, message):
        self.playback_status.setText("Exportação não concluída • " + message)
        self.playback_diagnostic.setText(message)
        from .runtime_diagnostics import record_runtime
        record_runtime(self, "exportação", message)

    def playback_export_finished(self):
        self.playback_export_worker = None
        self.playback_export_cancel = None
        self.playback_export_dialog.close()
        bounds = self.playback_clip_bounds
        trim_valid = not bounds or (self.playback_trim_end or bounds[1]) > (self.playback_trim_start or bounds[0])
        self.playback_export_btn.setEnabled(bool(self.playback_results.selectedItems()) and trim_valid
                                            and not self.playback_multi_check.isChecked())

    def playback_search_finished(self):
        self.playback_search_worker = None
        from .playback_layout import set_day_busy
        if not getattr(self, "_pending_day_search", False):set_day_busy(self,False)
        if getattr(self, "_pending_day_search", False):
            from .playback_layout import queue_day_search
            queue_day_search(self)
        device_id = self.playback_device_combo.currentData()
        device = self.db.get_device(device_id) if device_id is not None else None
        identity = " ".join(str(device[key] or "") for key in ("manufacturer", "provider")) if device else ""
        web_url = (device["web_url"] or "").strip() if device else ""
        web_ok = urlparse(web_url).scheme in ("http", "https") and bool(urlparse(web_url).hostname)
        self.playback_search_btn.setEnabled(bool((is_cloud_device(device) or (device is not None and hik_sdk_settings(device)["enabled"]) or (web_ok and ("intelbras" in identity.lower() or uses_hikvision_recordings(device))))
                                                 and self.playback_channel_combo.count()))

    def open_playback_device_web(self):
        device_id = self.playback_device_combo.currentData()
        if device_id is None:
            return
        site_id = self.current_site_id
        self._open_web_services(self._device_web_services(device_id),
                                lambda: self.current_site_id == site_id
                                and self.playback_device_combo.currentData() == device_id)

    # ---------- events / health ----------
    def build_events_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        head = QLabel("EVENTOS")
        f = QFont(); f.setPointSize(18); f.setBold(True); head.setFont(f)
        layout.addWidget(head)
        self.event_table = QTableWidget(0, 5)
        self.event_table.setHorizontalHeaderLabels(["Data", "Severidade", "Tipo", "Equipamento", "Mensagem"])
        self.event_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.event_table)
        self.events_page = page
        self.config_tabs.addTab(page, "Eventos")

    def build_health_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        head = QLabel("SAÚDE DO CFTV")
        f = QFont(); f.setPointSize(18); f.setBold(True); head.setFont(f)
        layout.addWidget(head)
        self.health_label = QLabel()
        self.health_label.setWordWrap(True)
        self.health_label.setStyleSheet("padding:14px;background:#142331;border:1px solid #2a4452;border-radius:8px")
        layout.addWidget(self.health_label)

        channel_head = QLabel("CANAIS MONITORADOS")
        cf = QFont(); cf.setPointSize(12); cf.setBold(True); channel_head.setFont(cf)
        layout.addWidget(channel_head)
        self.channel_health_table = QTableWidget(0, 8)
        self.channel_health_table.setHorizontalHeaderLabels([
            "Equipamento", "Canal", "Estado", "Tipo", "IP configurado", "Protocolo", "Última mudança", "Detalhe"
        ])
        self.channel_health_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.channel_health_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.channel_health_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.channel_health_table, 1)

        note = QLabel(
            "O monitor usa consultas somente leitura e rotas RTSP já conhecidas. Falhas de canal são confirmadas em duas verificações consecutivas para reduzir falsos alertas. "
            "Quando o gravador informa o endpoint de uma câmera IP, o endereço configurado aparece na tabela."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#78968a;font-size:11px")
        layout.addWidget(note)
        button = QPushButton("Verificar agora")
        button.clicked.connect(self.monitor_tick)
        layout.addWidget(button, 0, Qt.AlignLeft)
        self.health_page = page
        self.config_tabs.addTab(page, "Saúde")

    # ---------- configuration ----------
    def build_configuration_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 14, 14, 14)
        head = QLabel("CONFIGURAÇÃO E MANUTENÇÃO")
        f = QFont(); f.setPointSize(16); f.setBold(True); head.setFont(f)
        outer.addWidget(head)
        help_text = QLabel("Cadastro, eventos, saúde e manutenção dos equipamentos neste painel.")
        help_text.setStyleSheet("color:#879f94")
        outer.addWidget(help_text)
        access = QPushButton("Alterar senha de acesso…")
        access.setObjectName("CompactAction")
        access.clicked.connect(self.change_app_password)
        from .action_flow import ActionFlowLayout
        actions_bar = QWidget()
        portability = ActionFlowLayout(actions_bar)
        portability.addWidget(access)
        performance_button = QPushButton("Analisar desempenho deste PC…")
        performance_button.setObjectName("CompactAction")
        from .pc_capacity_ui import open_pc_analysis
        performance_button.clicked.connect(lambda: open_pc_analysis(self))
        portability.addWidget(performance_button)
        from .runtime_diagnostics import open_runtime_panel
        runtime_button = QPushButton("Diagnóstico e atividade…")
        runtime_button.setObjectName("CompactAction")
        runtime_button.clicked.connect(lambda: open_runtime_panel(self))
        portability.addWidget(runtime_button)
        components_button=QPushButton('Componentes e SDKs…');components_button.setObjectName('CompactAction')
        from .components_ui import open_components
        components_button.clicked.connect(lambda:open_components(self));portability.addWidget(components_button)
        export_config = QPushButton("Exportar equipamentos…")
        export_config.setObjectName("CompactAction")
        export_config.clicked.connect(self.export_portable_configuration)
        import_config = QPushButton("Importar equipamentos…")
        import_config.setObjectName("CompactAction")
        import_config.clicked.connect(self.import_portable_configuration)
        portability.addWidget(export_config)
        portability.addWidget(import_config)
        outer.addWidget(actions_bar)
        from .access_control_ui import open_settings,toggle_role
        access_row=QHBoxLayout()
        permissions_button=QPushButton('Acesso e permissões…')
        permissions_button.clicked.connect(lambda:open_settings(self))
        permissions_button.setObjectName("CompactAction")
        portability.addWidget(permissions_button)
        self.access_role_label=QLabel('Controle de permissões desativado')
        access_row.addWidget(self.access_role_label)
        self.access_role_button=QPushButton('Entrar como administrador')
        self.access_role_button.clicked.connect(lambda:toggle_role(self))
        self.access_role_button.setObjectName("CompactAction")
        self.access_role_button.hide();portability.addWidget(self.access_role_button)
        access_row.addStretch();outer.addLayout(access_row)

        self.config_tabs = QTabWidget()
        outer.addWidget(self.config_tabs, 1)
        self.build_devices_tab()
        self.build_events_page()
        self.build_health_page()
        self.build_akdb_tab()
        self.build_updates_tab()
        self.pages.addWidget(page)

    @requires_permission('admin')
    def export_portable_configuration(self):
        from .config_transfer_ui import export_devices
        export_devices(self)

    @requires_permission('admin')
    def import_portable_configuration(self):
        from .config_transfer_ui import import_devices
        import_devices(self)

    def build_sites_section(self, layout):
        site_bar = QHBoxLayout()
        site_label = QLabel("SITE ATIVO")
        site_label.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px")
        self.site_combo = QComboBox()
        self.site_combo.setMinimumWidth(225)
        self.site_combo.setMaximumWidth(380)
        self.site_combo.setToolTip("Cada equipamento pertence a um Site; escolha o Site para operar")
        self.site_combo.currentIndexChanged.connect(self.select_site_from_combo)
        self.site_count_label = QLabel("Selecione um Site")
        self.site_count_label.setStyleSheet("color:#98b3bc")
        new_site = QPushButton("Novo Site")
        new_site.setObjectName("CompactAction")
        new_site.clicked.connect(self.add_site)
        manager_button = QToolButton()
        manager_button.setObjectName("CompactAction")
        manager_button.setText("Gerenciar Sites ▾")
        manager_button.setCheckable(True)
        site_bar.addWidget(site_label)
        site_bar.addWidget(self.site_combo)
        site_bar.addWidget(self.site_count_label)
        site_bar.addStretch()
        site_bar.addWidget(new_site)
        site_bar.addWidget(manager_button)
        layout.addLayout(site_bar)

        manager = QFrame()
        manager.setObjectName("SourcePane")
        manager.setVisible(False)
        manager_button.toggled.connect(manager.setVisible)
        site_layout = QVBoxLayout(manager)
        site_layout.setContentsMargins(8, 6, 8, 6)

        toolbar = QHBoxLayout()
        rename = QPushButton("Renomear")
        rename.setToolTip("Renomear o Site selecionado")
        rename.clicked.connect(self.rename_selected_site)
        more = QToolButton()
        more.setObjectName("ActionMenu")
        more.setText("Mais ▾")
        more.setPopupMode(QToolButton.InstantPopup)
        site_menu = QMenu(more)
        archive_action = site_menu.addAction("Arquivar Site")
        archive_action.triggered.connect(self.archive_selected_site)
        restore_action = site_menu.addAction("Ver arquivados / restaurar")
        restore_action.triggered.connect(self.show_archived_sites)
        site_menu.addSeparator()
        delete_action = site_menu.addAction("Excluir Site…")
        delete_action.triggered.connect(self.delete_selected_site)
        more.setMenu(site_menu)
        self._site_more_menu = site_menu
        for button in (rename,):
            button.setObjectName("CompactAction")
            toolbar.addWidget(button)
        toolbar.addWidget(more)
        toolbar.addStretch()
        site_layout.addLayout(toolbar)

        self.site_table = QTableWidget(0, 2)
        self.site_table.setHorizontalHeaderLabels(["Site", "Descrição"])
        self.site_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.site_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.site_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.site_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.site_table.cellClicked.connect(self.select_site_from_table)
        self.site_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.site_table.customContextMenuRequested.connect(self.show_site_context_menu)
        self.site_table.setMaximumHeight(145)
        site_layout.addWidget(self.site_table)
        hint = QLabel("Selecione um Site para torná-lo ativo. Ações raras ficam em Mais ▾ ou no botão direito.")
        hint.setStyleSheet("color:#809da8;font-size:10px")
        site_layout.addWidget(hint)
        layout.addWidget(manager)

    def build_devices_tab(self):
        """VMS-style device workspace: inventory on the left, context on the right."""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroller = QScrollArea(tab)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.build_sites_section(layout)

        primary = QHBoxLayout()
        add = QPushButton("Adicionar ▾")
        add.setToolTip("Adicionar equipamento manualmente")
        add_menu=QMenu(add)
        add_menu.addAction('Equipamento local / VPN…',self.add_device_manual)
        add_menu.addAction('Intelbras Cloud…',self.add_intelbras_cloud_bridge)
        add.setMenu(add_menu)
        edit = QPushButton("Editar")
        edit.setToolTip("Editar nome, tipo, fabricante e modelo")
        edit_menu=QMenu(edit)
        edit_menu.addAction('Cadastro e identificação…',self.edit_selected_device)
        edit_menu.addAction('Acesso Hikvision / SDK…',self.configure_hik_sdk)
        edit_menu.addAction('Esquecer credencial salva…',self.forget_selected_device_credential)
        edit_menu.aboutToShow.connect(lambda:edit_menu.actions()[1].setVisible(uses_hikvision_recordings(self.db.get_device(self.selected_device_id())) if self.selected_device_id() else False))
        edit.setMenu(edit_menu)
        diag = QPushButton("Diagnóstico…")
        diag.setToolTip("Executar diagnóstico somente leitura")
        diag_menu=QMenu(diag)
        diag_menu.addAction('Conectividade do equipamento',self.diagnose_selected)
        hik_diag=diag_menu.addAction('Compatibilidade Hikvision',self.diagnose_selected_hikvision)
        intel_diag=diag_menu.addAction('API Intelbras',self.diagnose_selected_intelbras_http)
        def filter_diagnostics():
            did=self.selected_device_id();device=self.db.get_device(did) if did else None
            provider=recorder_provider_hint(device) if device else ''
            hik_diag.setVisible(provider in {'hikvision','jfl'});intel_diag.setVisible(provider=='intelbras')
        diag_menu.aboutToShow.connect(filter_diagnostics);diag.setMenu(diag_menu)
        self.channels_button = QPushButton("Canais…")
        self.channels_button.setToolTip("Ler canais do gravador ou testar o stream da câmera IP selecionada")
        channels_menu=QMenu(self.channels_button)
        channels_menu.addAction('Ver canais cadastrados',self.show_saved_channels)
        channels_menu.addAction('Atualizar canais / testar stream',self.read_device_channels_or_stream)
        self.channels_button.setMenu(channels_menu)
        self.web_button = QPushButton("Abrir Web")
        self.web_button.setToolTip("Abrir a interface Web detectada do equipamento no navegador padrão")
        self.web_button.setEnabled(False)
        self.web_button.clicked.connect(self.open_selected_device_web)
        more = QToolButton()
        more.setObjectName("ActionMenu")
        more.setText("Mais ▾")
        more.setPopupMode(QToolButton.InstantPopup)
        device_menu = QMenu(more)
        export_profile = device_menu.addAction("Exportar perfil AKDB")
        export_profile.triggered.connect(self.export_selected_compatibility_report)
        device_menu.addSeparator()
        archive = device_menu.addAction("Arquivar equipamento…")
        archive.triggered.connect(self.archive_selected_device)
        ignore = device_menu.addAction("Ignorar descoberta")
        ignore.triggered.connect(self.ignore_selected_device)
        restore = device_menu.addAction("Ver arquivados / restaurar")
        restore.triggered.connect(self.show_archived_devices)
        device_menu.addSeparator()
        delete = device_menu.addAction("Excluir permanentemente…")
        delete.triggered.connect(self.delete_selected_device)
        more.setMenu(device_menu)
        self._device_more_menu = device_menu
        for button in (add, edit, diag, self.channels_button, self.web_button):
            button.setObjectName("CompactAction")
            primary.addWidget(button)
        primary.addWidget(more)
        primary.addStretch()

        # Discovery, evidence and enrollment share this single device manager.
        device_sections = QSplitter(Qt.Vertical)
        device_sections.setObjectName("equipmentSectionsSplitter")
        found = QFrame()
        found.setObjectName("SourcePane")
        found_layout = QVBoxLayout(found)
        found_layout.setContentsMargins(8, 6, 8, 6)
        found_header = QHBoxLayout()
        found_title = QLabel("DISPOSITIVOS LOCALIZADOS NA REDE")
        found_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px")
        self.devices_found_status = QLabel("Use Buscar para procurar equipamentos neste Site.")
        self.devices_found_status.setStyleSheet("color:#98b3bc")
        self.devices_find_btn = QPushButton("Buscar / atualizar")
        self.devices_find_btn.setObjectName("CompactAction")
        self.devices_find_btn.clicked.connect(self.start_discovery)
        self.devices_add_found_btn = QPushButton("Adicionar selecionado")
        self.devices_add_found_btn.setObjectName("CompactAction")
        self.devices_add_found_btn.setEnabled(False)
        self.devices_add_found_btn.clicked.connect(self.add_found_from_devices)
        found_more = QToolButton()
        found_more.setObjectName("ActionMenu")
        found_more.setText("Mais ▾")
        found_more.setPopupMode(QToolButton.InstantPopup)
        found_menu = QMenu(found_more)
        self.devices_found_channels_btn = found_menu.addAction("Canais")
        self.devices_found_channels_btn.setEnabled(False)
        self.devices_found_channels_btn.triggered.connect(lambda: self.act_on_found_device(self.read_device_channels_or_stream))
        self.devices_found_delete_btn = found_menu.addAction("Excluir")
        self.devices_found_delete_btn.setEnabled(False)
        self.devices_found_delete_btn.triggered.connect(lambda: self.act_on_found_device(self.delete_selected_device))
        found_more.setMenu(found_menu)
        self._discovery_more_menu = found_menu
        self.devices_web_found_btn = QPushButton("Web do encontrado")
        self.devices_web_found_btn.setObjectName("CompactAction")
        self.devices_web_found_btn.setToolTip("Abrir a página de configuração detectada no navegador padrão")
        self.devices_web_found_btn.setEnabled(False)
        self.devices_web_found_btn.clicked.connect(self.open_discovered_device_web)
        self.devices_report_found_btn = QPushButton("Relatório AKDB")
        self.devices_report_found_btn.setObjectName("CompactAction")
        self.devices_report_found_btn.setEnabled(False)
        self.devices_report_found_btn.clicked.connect(self.export_discovered_homologation_report)
        found_header.addWidget(found_title)
        found_header.addWidget(self.devices_found_status, 1)
        found_layout.addLayout(found_header)
        found_actions = QHBoxLayout()
        for button in (self.devices_find_btn, self.devices_add_found_btn,
                       self.devices_web_found_btn, self.devices_report_found_btn):
            found_actions.addWidget(button)
        found_actions.addWidget(found_more)
        found_actions.addStretch()
        found_layout.addLayout(found_actions)
        self.devices_found_table = QTableWidget(0, 6)
        self.devices_found_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.devices_found_table.setHorizontalHeaderLabels(["IP", "Tipo", "Modelo / AKDB", "Portas", "Estado", "Evidência"])
        self.devices_found_table.setColumnWidth(0, 125)
        self.devices_found_table.setColumnWidth(1, 125)
        self.devices_found_table.setColumnWidth(2, 260)
        self.devices_found_table.setColumnWidth(3, 95)
        self.devices_found_table.setColumnWidth(4, 165)
        self.devices_found_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.devices_found_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.devices_found_table.verticalHeader().setVisible(False)
        self.devices_found_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.devices_found_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.devices_found_table.itemSelectionChanged.connect(self._discovery_selection_changed)
        self.devices_found_table.cellDoubleClicked.connect(lambda _r, _c: self.add_found_from_devices())
        found_layout.addWidget(self.devices_found_table)
        self.devices_found_progress = QProgressBar()
        self.devices_found_progress.setRange(0, 1)
        self.devices_found_progress.setValue(0)
        found_layout.addWidget(self.devices_found_progress)
        details_button = QToolButton()
        details_button.setText("Detalhes da busca ▾")
        details_button.setCheckable(True)
        self.devices_discovery_log = QPlainTextEdit()
        self.devices_discovery_log.setReadOnly(True)
        self.devices_discovery_log.setMaximumHeight(105)
        self.devices_discovery_log.setVisible(False)
        details_button.toggled.connect(self.devices_discovery_log.setVisible)
        found_layout.addWidget(details_button, 0, Qt.AlignLeft)
        found_layout.addWidget(self.devices_discovery_log)
        found.setMinimumHeight(400)
        device_splitter = QSplitter(Qt.Horizontal)

        inventory = QFrame()
        inventory.setObjectName("SourcePane")
        inv = QVBoxLayout(inventory)
        inv.setContentsMargins(8, 8, 8, 8)
        inv.setSpacing(6)
        inv_title = QLabel("EQUIPAMENTOS CADASTRADOS NO SITE")
        inv_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px")
        inv.addWidget(inv_title)
        self.device_inventory_count = QLabel("0 cadastrados • 0 online")
        self.device_inventory_count.setStyleSheet("color:#98b3bc")
        inv.addWidget(self.device_inventory_count)
        inv.addLayout(primary)
        self.device_filter = QLineEdit()
        self.device_filter.setPlaceholderText("Filtrar por nome, IP, fabricante ou modelo…")
        self.device_filter.textChanged.connect(self.refresh_device_filter)
        inv.addWidget(self.device_filter)

        self.dev_table = QTableWidget(0, 9)
        self.dev_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dev_table.setHorizontalHeaderLabels(["Nome", "IP", "Tipo", "Fabricante / modelo", "Estado", "Canais", "Áudio", "Confiança", "Credencial"])
        self.dev_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dev_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.dev_table.setColumnWidth(5, 155)
        self.dev_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.dev_table.verticalHeader().setVisible(False)
        self.dev_table.setAlternatingRowColors(True)
        self.dev_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dev_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.dev_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.dev_table.customContextMenuRequested.connect(self.show_device_context_menu)
        self.dev_table.itemSelectionChanged.connect(self._device_selection_changed)
        self.dev_table.cellDoubleClicked.connect(lambda _row, _col: self.edit_selected_device())
        inv.addWidget(self.dev_table, 1)
        device_splitter.addWidget(inventory)

        details = QFrame()
        details.setObjectName("InspectorPane")
        details_outer = QVBoxLayout(details)
        details_outer.setContentsMargins(0, 0, 0, 0)
        details_scroll = QScrollArea(details)
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.NoFrame)
        details_content = QWidget()
        det = QVBoxLayout(details_content)
        det.setContentsMargins(12, 12, 12, 12)
        det.setSpacing(8)
        det_title = QLabel("DETALHES DO EQUIPAMENTO")
        det_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px")
        det.addWidget(det_title)
        self.device_detail_name = QLabel("Selecione um equipamento")
        self.device_detail_name.setStyleSheet("font-size:17px;font-weight:700;color:#e8f2f5")
        self.device_detail_name.setWordWrap(True)
        det.addWidget(self.device_detail_name)
        self.device_detail_identity = QLabel("Identidade e endereço aparecerão aqui.")
        self.device_detail_identity.setWordWrap(True)
        self.device_detail_identity.setStyleSheet("color:#a6bec4")
        det.addWidget(self.device_detail_identity)
        self.device_detail_evidence=QLabel('')
        self.device_detail_evidence.setTextFormat(Qt.PlainText)
        self.device_detail_evidence.setWordWrap(True)
        self.device_detail_evidence.setStyleSheet('color:#98b3bc;font-size:10px')
        det.addWidget(self.device_detail_evidence)

        cap_title = QLabel("CAPACIDADES")
        cap_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px;margin-top:6px")
        det.addWidget(cap_title)
        self.device_detail_capabilities = QLabel("—")
        self.device_detail_capabilities.setWordWrap(True)
        self.device_detail_capabilities.setStyleSheet("padding:8px;background:#0d1925;border-radius:6px;color:#a8c3b7")
        det.addWidget(self.device_detail_capabilities)

        proto_title = QLabel("ACESSO LOCAL / PROTOCOLOS")
        proto_title.setStyleSheet("font-weight:700;color:#c3d6db;font-size:11px;margin-top:6px")
        det.addWidget(proto_title)
        self.device_detail_protocols = QLabel("—")
        self.device_detail_protocols.setWordWrap(True)
        self.device_detail_protocols.setStyleSheet("padding:8px;background:#0d1925;border-radius:6px;color:#a8c3b7")
        det.addWidget(self.device_detail_protocols)

        quick = QHBoxLayout()
        self.device_live_btn = QPushButton("Abrir no Live View")
        self.device_live_btn.setObjectName("CompactAction")
        self.device_live_btn.setEnabled(False)
        self.device_live_btn.clicked.connect(self.open_selected_device_in_live_view)
        self.device_details_channels_btn = QPushButton("Canais / Stream")
        self.device_details_channels_btn.setObjectName("CompactAction")
        self.device_details_channels_btn.setEnabled(False)
        self.device_details_channels_btn.clicked.connect(self.read_device_channels_or_stream)
        quick.addWidget(self.device_live_btn)
        quick.addWidget(self.device_details_channels_btn)
        det.addLayout(quick)
        self.hik_sdk_button=QPushButton("Acesso Hikvision / SDK…")
        self.hik_sdk_button.setObjectName("CompactAction")
        self.hik_sdk_button.clicked.connect(self.configure_hik_sdk)
        det.addWidget(self.hik_sdk_button)
        det.addStretch()
        hint = QLabel("Duplo clique edita. Botão direito abre as ações completas do equipamento.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#809da8;font-size:10px")
        det.addWidget(hint)
        details_scroll.setWidget(details_content)
        details_outer.addWidget(details_scroll)
        device_splitter.addWidget(details)
        device_splitter.setMinimumHeight(280)
        device_splitter.setStretchFactor(0, 3)
        device_splitter.setStretchFactor(1, 2)
        device_splitter.setSizes([780, 420])
        device_sections.addWidget(device_splitter)
        device_sections.addWidget(found)
        device_sections.setStretchFactor(0, 3)
        device_sections.setStretchFactor(1, 2)
        device_sections.setSizes([460, 400])
        device_sections.setMinimumHeight(740)
        layout.addWidget(device_sections, 1)
        self.build_equipment_log_panel(layout)
        body.setMinimumHeight(910)
        scroller.setWidget(body)
        outer.addWidget(scroller)
        self.config_tabs.addTab(tab, "Equipamentos")

    def build_equipment_log_panel(self, layout):
        toggle = QToolButton()
        toggle.setText("Logs e diagnóstico ▾")
        toggle.setCheckable(True)
        layout.addWidget(toggle, 0, Qt.AlignLeft)
        panel = QFrame()
        panel.setObjectName("SourcePane")
        panel.setVisible(False)
        toggle.toggled.connect(panel.setVisible)
        toggle.toggled.connect(lambda open_: self.refresh_equipment_logs() if open_ else None)
        self.equipment_log_panel = panel
        inside = QVBoxLayout(panel)
        controls = QHBoxLayout()
        self.equipment_log_source = QComboBox()
        for title, key in (("Canais do Site", "channels"), ("Leitura RTSP", "rtsp"),
                           ("Ao vivo (sessão)", "live"), ("Atualizações", "update"), ("Falhas", "fault")):
            self.equipment_log_source.addItem(title, key)
        self.equipment_log_source.currentIndexChanged.connect(self.refresh_equipment_logs)
        self.equipment_log_filter = QLineEdit()
        self.equipment_log_filter.setPlaceholderText("Filtrar linhas…")
        self.equipment_log_filter.textChanged.connect(self.refresh_equipment_logs)
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh_equipment_logs)
        copy = QPushButton("Copiar texto")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.equipment_log_text.toPlainText()))
        controls.addWidget(self.equipment_log_source)
        controls.addWidget(self.equipment_log_filter, 1)
        controls.addWidget(refresh)
        controls.addWidget(copy)
        inside.addLayout(controls)
        self.equipment_log_text = QPlainTextEdit()
        self.equipment_log_text.setReadOnly(True)
        self.equipment_log_text.setMaximumHeight(175)
        inside.addWidget(self.equipment_log_text)
        layout.addWidget(panel)

    def refresh_equipment_logs(self, *_args):
        if not self.equipment_log_panel.isVisible():
            return
        source = self.equipment_log_source.currentData()
        if source == "channels":
            lines = []
            for device in self.db.list_devices(self.current_site_id):
                lines.append(f"{device_visual_name(device)} ({device['ip']}):")
                channels = self.db.list_recorder_channels(device["id"])
                if not channels:
                    lines.append("  Sem canais lidos.")
                for channel in channels:
                    detail = sanitize_log_text(channel["detail"] or "")
                    lines.append(f"  Canal {channel['channel_no']}: {'vídeo confirmado' if channel['available'] else 'sem vídeo confirmado'} • {detail}")
            contents = "\n".join(lines) if lines else "Nenhum equipamento neste Site."
        elif source == "live":
            contents = sanitize_log_text("\n".join(
                f"Visão {index + 1}: {line}" for index, lines in self.live_diag_lines.items() for line in lines[-50:]
            )) or "Ainda não há diagnóstico de vídeo nesta sessão."
        else:
            contents = read_log_tail(data_dir() / "logs", source)
        self.equipment_log_text.setPlainText(filter_log_lines(contents, self.equipment_log_filter.text()))

    def build_akdb_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        try:
            shared = sync_shared_akdb()
            pending = " • envio pendente" if shared.get("upload_pending") else ""
            shared_text = (
                f"AKDB schema {shared.get('schema_version')} • Core r{shared.get('core_revision')} • "
                f"Sentinel ext r{shared.get('domain_revision')} • geração local {shared.get('local_generation')}"
                f"{pending}\n{shared['records']} identidades • {shared['evidence']} evidências • "
                f"{shared.get('field_reports', 0)} relatório(s) • {shared['path']}"
            )
        except Exception as exc:
            shared_text = f"AKDB Core compartilhada indisponível nesta sessão: {exc}"
        info = QLabel(
            "AKDB — Base de conhecimento compartilhada entre Artin Sentinel, Artin NetLens e Artin RescNow. "
            "A identidade central usa IDs estáveis; cada aplicativo mantém apenas extensões do seu domínio. "
            "Detecção automática, testes de campo, homologação e overrides do operador permanecem separados.\n"
            + shared_text
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        catalog_actions=QHBoxLayout()
        from .knowledge_ui import open_manufacturers,open_catalog
        brands_button=QPushButton('Fabricantes e cores…');brands_button.setObjectName('CompactAction')
        brands_button.clicked.connect(lambda:open_manufacturers(self))
        catalog_button=QPushButton('Explorar modelos…');catalog_button.setObjectName('CompactAction')
        catalog_button.clicked.connect(lambda:open_catalog(self))
        catalog_actions.addWidget(brands_button);catalog_actions.addWidget(catalog_button);catalog_actions.addStretch()
        layout.addLayout(catalog_actions)

        sync_box = QGroupBox("AKDB Sync + Field Learning")
        sync_layout = QVBoxLayout(sync_box)
        self.akdb_sync_status = QLabel("Pronto para verificar a base oficial.")
        self.akdb_sync_status.setWordWrap(True)
        self.akdb_sync_status.setStyleSheet("color:#98b3bc")
        sync_layout.addWidget(self.akdb_sync_status)

        sync_form = QFormLayout()
        self.akdb_manifest_edit = QLineEdit(self.akdb_sync_settings.manifest_url)
        self.akdb_manifest_edit.setToolTip("Manifesto oficial da AKDB. O bundle é validado por SHA-256 antes de ser aplicado.")
        self.akdb_repo_edit = QLineEdit(self.akdb_sync_settings.github_repo)
        self.akdb_repo_edit.setToolTip("Repositório de caixa de entrada. Use um token GitHub fine-grained limitado a este repositório.")
        self.akdb_check_with_updates = QCheckBox("Verificar AKDB junto com a atualização do aplicativo")
        self.akdb_check_with_updates.setChecked(self.akdb_sync_settings.check_with_app_updates)
        sync_form.addRow("Manifesto oficial:", self.akdb_manifest_edit)
        sync_form.addRow("Inbox GitHub:", self.akdb_repo_edit)
        sync_form.addRow("", self.akdb_check_with_updates)
        sync_layout.addLayout(sync_form)

        sync_buttons = QHBoxLayout()
        self.akdb_save_sync_btn = QPushButton("Salvar")
        self.akdb_save_sync_btn.setObjectName("CompactAction")
        self.akdb_save_sync_btn.clicked.connect(self.save_akdb_sync_ui_settings)
        self.akdb_token_btn = QPushButton("Configurar token GitHub…")
        self.akdb_token_btn.setObjectName("CompactAction")
        self.akdb_token_btn.clicked.connect(self.configure_akdb_submission_token)
        self.akdb_check_btn = QPushButton("Verificar AKDB")
        self.akdb_check_btn.setObjectName("CompactAction")
        self.akdb_check_btn.clicked.connect(lambda: self.check_akdb_updates(False))
        self.akdb_preview_btn = QPushButton("Ver alterações")
        self.akdb_preview_btn.setObjectName("CompactAction")
        self.akdb_preview_btn.setEnabled(False)
        self.akdb_preview_btn.clicked.connect(self.preview_akdb_changes)
        self.akdb_apply_btn = QPushButton("Atualizar base")
        self.akdb_apply_btn.setObjectName("CompactAction")
        self.akdb_apply_btn.setEnabled(False)
        self.akdb_apply_btn.clicked.connect(self.apply_akdb_update_ui)
        self.akdb_submit_btn = QPushButton("Revisar candidatos…")
        self.akdb_submit_btn.setObjectName("CompactAction")
        self.akdb_submit_btn.clicked.connect(self.review_akdb_candidates)
        for button in (self.akdb_save_sync_btn, self.akdb_token_btn, self.akdb_check_btn, self.akdb_preview_btn, self.akdb_apply_btn, self.akdb_submit_btn):
            sync_buttons.addWidget(button)
        sync_buttons.addStretch()
        sync_layout.addLayout(sync_buttons)
        layout.addWidget(sync_box)
        self.refresh_akdb_sync_status()

        rows = public_summary()
        table = QTableWidget(len(rows), 15)
        table.setHorizontalHeaderLabels([
            "AKDB ID", "Fabricante", "Família / modelo", "Tipo de equipamento", "Subtipo", "Provider",
            "Família de protocolo", "Streams / vídeo", "Áudio / PTZ", "Protocolos locais",
            "Estratégia", "Homologação", "Domínios", "Origem / revisão", "Observações",
        ])
        table.horizontalHeader().setSectionResizeMode(14, QHeaderView.Stretch)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        for r, item in enumerate(rows):
            audio_text = item.get("audio_mode", "unknown")
            if item.get("audio_codecs"):
                audio_text += " • " + ", ".join(item["audio_codecs"])
            ptz = item.get("ptz_mode") or "unknown"
            stream_text = str(item.get("stream_count") or "—")
            if item.get("video_codecs"):
                stream_text += " • " + ", ".join(item["video_codecs"])
            local_protocols = " • ".join(item.get("native_protocols") or []) or "—"
            model_text = item.get("family") or item.get("core_model") or "—"
            domains = ", ".join(item.get("domains") or ["sentinel"])
            provenance = ", ".join(item.get("provenance") or []) or "—"
            provenance += f" • r{int(item.get('revision') or 1)}"
            strategy = " → ".join(item.get("preferred_strategies") or []) or "—"
            vals = (
                item.get("stable_id") or item["key"], item["manufacturer"], model_text,
                canonical_type_label(item.get("canonical_type") or "unknown"), item.get("subtype") or "—", item["provider"],
                item["protocol_family"], stream_text, f"{audio_text} / PTZ {ptz}", local_protocols, strategy,
                item.get("core_validation") or item["validation"], domains, provenance,
                "; ".join(item["notes"]) or "—",
            )
            for c, value in enumerate(vals):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        self.config_tabs.addTab(tab, "AKDB")


    def _akdb_settings_from_ui(self) -> AkdbSyncSettings:
        settings = self.akdb_sync_settings
        if hasattr(self, "akdb_manifest_edit"):
            settings.manifest_url = self.akdb_manifest_edit.text().strip()
            settings.github_repo = self.akdb_repo_edit.text().strip()
            settings.auto_submit = False
            settings.check_with_app_updates = bool(self.akdb_check_with_updates.isChecked())
        return settings

    @requires_permission('admin')
    def save_akdb_sync_ui_settings(self):
        self.akdb_sync_settings = self._akdb_settings_from_ui()
        save_akdb_sync_settings(self.akdb_sync_settings, data_dir())
        self.refresh_akdb_sync_status("Configuração da AKDB Sync salva.")

    @requires_permission('admin')
    def configure_akdb_submission_token(self):
        current = bool(get_submission_token())
        text, ok = QInputDialog.getText(
            self, "Token de submissão AKDB",
            "Informe um token GitHub fine-grained com acesso ao repositório configurado.\n"
            "Deixe vazio e confirme para remover o token atual.",
            QLineEdit.Password,
        )
        if not ok:
            return
        try:
            set_submission_token(text)
        except Exception as exc:
            QMessageBox.warning(self, "AKDB Sync", f"Não foi possível gravar o token no keyring.\n\n{exc}")
            return
        self.refresh_akdb_sync_status("Token GitHub configurado no keyring." if text.strip() else "Token GitHub removido.")
        if current and not text.strip():
            self.akdb_sync_settings.auto_submit = False
            save_akdb_sync_settings(self.akdb_sync_settings, data_dir())

    def refresh_akdb_sync_status(self, prefix: str = ""):
        if not hasattr(self, "akdb_sync_status"):
            return
        try:
            shared = sync_shared_akdb()
            token = "token OK" if get_submission_token() else "token ausente"
            parts = [
                f"Core r{shared.get('core_revision', 0)} • release oficial r{shared.get('official_release_revision', 0)}",
                f"geração local {shared.get('local_generation', 0)}",
                f"{shared.get('pending_submissions', 0)} envio(s) pendente(s)",
                token,
            ]
            text = " • ".join(parts)
            if prefix:
                text = prefix + "\n" + text
            self.akdb_sync_status.setText(text)
        except Exception as exc:
            self.akdb_sync_status.setText(f"AKDB Sync indisponível: {exc}")

    def _set_akdb_busy(self, busy: bool, text: str = ""):
        for name in ("akdb_save_sync_btn", "akdb_token_btn", "akdb_check_btn", "akdb_submit_btn"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(not busy)
        if hasattr(self, "akdb_apply_btn"):
            self.akdb_apply_btn.setEnabled((not busy) and bool(self.akdb_remote_result and self.akdb_remote_result.get("available")))
        if hasattr(self, "akdb_preview_btn"):
            self.akdb_preview_btn.setEnabled((not busy) and bool(self.akdb_remote_result and self.akdb_remote_result.get("preview")))
        if text and hasattr(self, "akdb_sync_status"):
            self.akdb_sync_status.setText(text)

    def check_akdb_updates(self, silent: bool = False):
        if self.akdb_sync_worker is not None:
            return
        if not silent:
            self.akdb_sync_settings = self._akdb_settings_from_ui()
            save_akdb_sync_settings(self.akdb_sync_settings, data_dir())
        if not self.akdb_sync_settings.manifest_url:
            if not silent:
                QMessageBox.information(self, "AKDB Sync", "Configure primeiro o manifesto oficial da AKDB.")
            return
        self.akdb_remote_result = None
        self._set_akdb_busy(True, "Verificando revisão oficial da AKDB…")
        worker = Worker(check_official_update, manifest_url=self.akdb_sync_settings.manifest_url)
        self.akdb_sync_worker = worker
        worker.signals.result.connect(lambda result, s=silent: self.akdb_check_result(result, s))
        worker.signals.error.connect(lambda error, s=silent: self.akdb_check_error(error, s))
        worker.signals.finished.connect(self._akdb_check_finished)
        self.start_qt_worker(worker)

    def _akdb_check_finished(self):
        self.akdb_sync_worker = None
        self._set_akdb_busy(False)

    def akdb_check_result(self, result: dict, silent: bool = False):
        self.akdb_remote_result = result
        self.akdb_preview_btn.setEnabled(bool(result.get("preview")))
        manifest = result.get("manifest") or {}
        delta = result.get("delta") or {}
        available = bool(result.get("available"))
        summary = (
            f"AKDB oficial r{int(manifest.get('release_revision') or 0)} • "
            f"+{int(delta.get('new_records') or 0)} identidade(s) • "
            f"~{int(delta.get('updated_records') or 0)} identidade(s) editada(s) • "
            f"+{int(delta.get('new_extensions') or 0)}/~{int(delta.get('updated_extensions') or 0)} extensão(ões)"
        )
        if result.get("blocked_reason"):
            self.akdb_sync_status.setText(summary + "\n" + str(result["blocked_reason"]))
            self.akdb_apply_btn.setEnabled(False)
            if not silent:
                QMessageBox.warning(self, "Revisão da AKDB requer análise", str(result["blocked_reason"]))
        elif available:
            self.akdb_sync_status.setText(summary + "\nAtualização da Base de Conhecimento disponível para revisão.")
            self.akdb_apply_btn.setEnabled(True)
            if not silent:
                QMessageBox.information(
                    self, "Atualização da AKDB disponível",
                    summary + "\n\nA atualização altera apenas o Core oficial. Evidências e candidatos locais serão preservados."
                )
            else:
                self.bottom_notice.setText("Atualização da AKDB disponível")
        else:
            self.akdb_sync_status.setText(summary + "\nBase oficial já sincronizada.")
            self.akdb_apply_btn.setEnabled(False)

    def akdb_check_error(self, error: str, silent: bool = False):
        self.akdb_remote_result = None
        self.akdb_preview_btn.setEnabled(False)
        self.akdb_apply_btn.setEnabled(False)
        self.refresh_akdb_sync_status(f"Não foi possível verificar a AKDB oficial: {error}")
        if not silent:
            QMessageBox.warning(self, "AKDB Sync", f"Falha ao verificar a Base de Conhecimento.\n\n{error}")

    def preview_akdb_changes(self):
        result = self.akdb_remote_result or {}
        entries = result.get("preview") or []
        if not entries:
            QMessageBox.information(self, "Prévia AKDB", "Nenhuma alteração para exibir. Verifique a AKDB novamente.")
            return
        names = {"new": "Nova", "updated": "Editada", "conflict": "Conflito"}
        lines = [f"Revisão oficial r{int((result.get('manifest') or {}).get('release_revision') or 0)}", ""]
        if result.get("blocked_reason"):
            lines.extend((str(result["blocked_reason"]), ""))
        for item in entries:
            scope = "Identidade" if item.get("scope") == "identity" else "Extensão"
            lines.append(f"{names.get(item.get('status'), 'Alteração')} • {scope} • {item.get('label', '')}")
            lines.append(f"ID: {item.get('stable_id', '')} • revisão {item.get('local_revision', 0)} → {item.get('incoming_revision', 0)}")
            if item.get("changed_fields"):
                lines.append("Campos alterados: " + ", ".join(item["changed_fields"]))
            lines.append("")
        lines.append("Os valores e as evidências locais não são exibidos nesta prévia.")
        dialog = QDialog(self)
        dialog.setWindowTitle("Prévia das alterações da AKDB")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        detail = QPlainTextEdit(dialog)
        detail.setReadOnly(True)
        detail.setPlainText("\n".join(lines))
        layout.addWidget(detail)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    @requires_permission('admin')
    def apply_akdb_update_ui(self):
        result = self.akdb_remote_result
        if not result or not result.get("available"):
            QMessageBox.information(self, "AKDB Sync", "Nenhuma revisão nova da AKDB está pronta para aplicar.")
            return
        delta = result.get("delta") or {}
        answer = QMessageBox.question(
            self, "Atualizar Base de Conhecimento",
            f"Aplicar a revisão oficial da AKDB?\n\n"
            f"Novas identidades: {int(delta.get('new_records') or 0)}\n"
            f"Identidades editadas: {int(delta.get('updated_records') or 0)}\n"
            f"Novas extensões: {int(delta.get('new_extensions') or 0)}\n"
            f"Extensões editadas: {int(delta.get('updated_extensions') or 0)}\n\n"
            "O overlay local, relatórios de campo e fila de envio serão preservados.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        self._set_akdb_busy(True, "Aplicando revisão oficial da AKDB…")
        worker = Worker(apply_official_update, result)
        self.akdb_apply_worker = worker
        worker.signals.result.connect(self.akdb_apply_result)
        worker.signals.error.connect(lambda error: QMessageBox.warning(self, "AKDB Sync", f"Atualização não aplicada.\n\n{error}"))
        worker.signals.finished.connect(self._akdb_apply_finished)
        self.start_qt_worker(worker)

    def _akdb_apply_finished(self):
        self.akdb_apply_worker = None
        self._set_akdb_busy(False)

    def akdb_apply_result(self, result: dict):
        if self.akdb_remote_result is not None:
            self.akdb_remote_result["available"] = False
        self.akdb_apply_btn.setEnabled(False)
        self.refresh_akdb_sync_status(
            f"AKDB oficial atualizada • {result.get('records_changed', 0)} identidade(s) • "
            f"{result.get('extensions_changed', 0)} extensão(ões)."
        )
        QMessageBox.information(
            self, "AKDB atualizada",
            "A revisão oficial foi aplicada. Conhecimento local e candidatos pendentes permaneceram separados."
        )

    def review_akdb_candidates(self):
        try:
            proposals = pending_proposals()
        except Exception as exc:
            QMessageBox.warning(self, "AKDB", f"Não foi possível ler os candidatos.\n\n{exc}")
            return
        if not proposals:
            QMessageBox.information(self, "AKDB", "Não há candidatos pendentes para revisão.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Revisar contribuições para a AKDB")
        dialog.resize(800, 620)
        layout = QVBoxLayout(dialog)
        note = QLabel("Selecione um candidato. A comparação usa a identidade oficial instalada; confira os dados sanitizados antes de exportar ou enviar.")
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(proposals), 5, dialog)
        table.setHorizontalHeaderLabels(["ID", "Fabricante", "Modelo", "Comparação oficial", "Estado"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for row, proposal in enumerate(proposals):
            for col, value in enumerate((proposal["report_id"], proposal["manufacturer"], proposal["model"],
                                         proposal["comparison"], proposal["state"])):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        detail = QPlainTextEdit(dialog)
        detail.setReadOnly(True)
        layout.addWidget(detail)

        def selected():
            row = table.currentRow()
            return proposals[row] if 0 <= row < len(proposals) else None

        def show_detail():
            proposal = selected()
            if proposal:
                detail.setPlainText(json.dumps({"comparacao": proposal["comparison"],
                                                "campos_diferentes": proposal["changed_fields"],
                                                "oficial": proposal["official"],
                                                "conteudo_da_proposta": proposal["report"]},
                                               ensure_ascii=False, indent=2))

        table.currentCellChanged.connect(lambda *_: show_detail())
        table.selectRow(0)
        show_detail()
        actions = QHBoxLayout()
        export_btn = QPushButton("Exportar proposta…", dialog)
        send_btn = QPushButton("Enviar proposta…", dialog)
        close_btn = QPushButton("Fechar", dialog)

        def do_export():
            proposal = selected()
            if not proposal:
                return
            path, _ = QFileDialog.getSaveFileName(dialog, "Exportar contribuição AKDB",
                                                  f"akdb-proposta-{proposal['report_id']}.json", "JSON (*.json)")
            if path:
                try:
                    export_proposals(path, [proposal])
                    QMessageBox.information(dialog, "AKDB", f"Proposta exportada para revisão:\n{path}")
                except Exception as exc:
                    QMessageBox.warning(dialog, "AKDB", f"Não foi possível exportar.\n\n{exc}")

        def do_send():
            proposal = selected()
            if not proposal:
                return
            if not get_submission_token():
                QMessageBox.information(dialog, "AKDB", "Configure o token GitHub antes de enviar.")
                return
            answer = QMessageBox.question(dialog, "Enviar proposta AKDB",
                f"Enviar a proposta #{proposal['report_id']} para {self.akdb_repo_edit.text().strip()}/"
                f"{self.akdb_sync_settings.github_inbox}?\n\n"
                "Confira o conteúdo exibido: a proposta ficará no repositório para revisão e não será incorporada automaticamente ao Core.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                dialog.accept()
                self.submit_akdb_pending(proposal)

        export_btn.clicked.connect(do_export)
        send_btn.clicked.connect(do_send)
        close_btn.clicked.connect(dialog.reject)
        for button in (export_btn, send_btn, close_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        dialog.exec()

    @requires_permission('admin')
    def submit_akdb_pending(self, proposal: dict):
        if self.akdb_submit_worker is not None:
            return
        self.akdb_sync_settings = self._akdb_settings_from_ui()
        save_akdb_sync_settings(self.akdb_sync_settings, data_dir())
        if not get_submission_token():
            QMessageBox.information(self, "AKDB Sync", "Configure primeiro o token GitHub da caixa de entrada.")
            return
        self._set_akdb_busy(True, "Enviando proposta revisada para a caixa de entrada…")
        worker = Worker(submit_pending, settings=self.akdb_sync_settings,
                        reviewed={proposal["report_id"]: proposal["review_sha256"]}, limit=1)
        self.akdb_submit_worker = worker
        worker.signals.result.connect(self.akdb_submit_result)
        worker.signals.error.connect(self.akdb_submit_error)
        worker.signals.finished.connect(self._akdb_submit_finished)
        self.start_qt_worker(worker)

    def _akdb_submit_finished(self):
        self.akdb_submit_worker = None
        self._set_akdb_busy(False)

    def akdb_submit_result(self, result: dict):
        sent = len(result.get("submitted") or [])
        failed = len(result.get("failed") or [])
        self.refresh_akdb_sync_status(f"AKDB Inbox: {sent} enviado(s) • {failed} falha(s).")
        if sent or failed:
            QMessageBox.information(self, "AKDB Sync", f"Envios concluídos: {sent}\nFalhas: {failed}")

    def akdb_submit_error(self, error: str):
        self.refresh_akdb_sync_status(f"Falha no envio AKDB: {error}")
        QMessageBox.warning(self, "AKDB Sync", f"Não foi possível enviar os candidatos.\n\n{error}")


    def build_updates_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title = QLabel("CENTRO DE ATUALIZAÇÕES")
        f = QFont(); f.setPointSize(13); f.setBold(True); title.setFont(f)
        layout.addWidget(title)

        info = QLabel(
            "O Sentinel verifica apenas metadados automaticamente. Download e instalação sempre exigem confirmação. "
            "O pacote é validado por SHA-256 antes de qualquer instalador ser executado; assinatura Ed25519 pode ser "
            "exigida quando a chave pública oficial estiver provisionada."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#98b3bc")
        layout.addWidget(info)

        status_box = QGroupBox("Versão instalada")
        status_layout = QVBoxLayout(status_box)
        self.update_version_label = QLabel(f"Artin Sentinel {__version__}")
        vf = QFont(); vf.setPointSize(15); vf.setBold(True); self.update_version_label.setFont(vf)
        self.update_status_label = QLabel("Nenhuma verificação executada nesta sessão.")
        self.update_status_label.setWordWrap(True)
        self.update_status_label.setStyleSheet("color:#98b3bc")
        status_layout.addWidget(self.update_version_label)
        status_layout.addWidget(self.update_status_label)
        layout.addWidget(status_box)

        source_box = QGroupBox("Fonte ArtinUpdates")
        form = QFormLayout(source_box)
        self.update_source_edit = QLineEdit(self.update_settings.manifest_base_url)
        self.update_source_edit.setPlaceholderText("https://.../ArtinUpdates  (gera /sentinel/stable.json ou beta.json)")
        self.update_source_edit.setToolTip(
            "URL base do repositório/serviço ArtinUpdates. Também aceita uma URL direta para um manifesto .json."
        )
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItem("Stable", "stable")
        self.update_channel_combo.addItem("Beta", "beta")
        idx = self.update_channel_combo.findData(self.update_settings.channel)
        self.update_channel_combo.setCurrentIndex(max(0, idx))
        self.update_startup_check = QCheckBox("Verificar atualizações ao iniciar")
        self.update_startup_check.setChecked(self.update_settings.check_on_startup)
        self.update_require_signature = QCheckBox("Exigir assinatura Ed25519")
        self.update_require_signature.setChecked(self.update_settings.require_signature)
        self.update_require_signature.setToolTip(
            "Ative somente depois de provisionar trusted-update-keys.json com a chave pública oficial."
        )
        form.addRow("Manifesto / base:", self.update_source_edit)
        key_row = QHBoxLayout()
        self.update_private_token = QLineEdit()
        self.update_private_token.setEchoMode(QLineEdit.Password)
        self.update_private_token.setPlaceholderText("Chave individual entregue pelo administrador")
        save_key = QPushButton("Salvar chave")
        save_key.clicked.connect(self.save_private_update_token)
        key_row.addWidget(self.update_private_token, 1)
        key_row.addWidget(save_key)
        form.addRow("Acesso privado:", key_row)
        form.addRow("Canal:", self.update_channel_combo)
        form.addRow("", self.update_startup_check)
        form.addRow("", self.update_require_signature)
        layout.addWidget(source_box)

        netsdk_box = QGroupBox("Componente opcional • Intelbras NetSDK")
        netsdk_layout = QVBoxLayout(netsdk_box)
        self.netsdk_component_status = QLabel("")
        self.netsdk_component_status.setWordWrap(True)
        self.netsdk_component_status.setStyleSheet("color:#98b3bc")
        netsdk_layout.addWidget(self.netsdk_component_status)
        netsdk_buttons = QHBoxLayout()
        self.netsdk_import_btn = QPushButton("Instalar / importar NetSDK Intelbras…")
        self.netsdk_import_btn.setObjectName("CompactAction")
        self.netsdk_import_btn.setToolTip(
            "Selecione uma vez o ZIP oficial General_NetSDK_3.050_PlaySDK_3.042.zip. "
            "O runtime será salvo na pasta persistente do usuário e reutilizado nos próximos updates."
        )
        self.netsdk_import_btn.clicked.connect(self.import_intelbras_netsdk_ui)
        netsdk_buttons.addWidget(self.netsdk_import_btn)
        self.netsdk_refresh_btn = QPushButton("Revalidar")
        self.netsdk_refresh_btn.setObjectName("CompactAction")
        self.netsdk_refresh_btn.clicked.connect(self.refresh_intelbras_netsdk_component_status)
        netsdk_buttons.addWidget(self.netsdk_refresh_btn)
        netsdk_buttons.addStretch()
        netsdk_layout.addLayout(netsdk_buttons)
        layout.addWidget(netsdk_box)
        self.refresh_intelbras_netsdk_component_status()

        buttons = QHBoxLayout()
        self.update_save_btn = QPushButton("Salvar configurações")
        self.update_save_btn.setObjectName("CompactAction")
        self.update_save_btn.clicked.connect(self.save_update_ui_settings)
        self.update_check_btn = QPushButton("Verificar agora")
        self.update_check_btn.setObjectName("CompactAction")
        self.update_check_btn.clicked.connect(lambda: self.check_for_updates(False))
        self.update_install_btn = QPushButton("Baixar e instalar")
        self.update_install_btn.setObjectName("CompactAction")
        self.update_install_btn.setEnabled(False)
        self.update_install_btn.clicked.connect(self.download_and_install_update)
        self.update_release_btn = QPushButton("Abrir página da versão")
        self.update_release_btn.setObjectName("CompactAction")
        self.update_release_btn.setEnabled(False)
        self.update_release_btn.clicked.connect(self.open_update_release_page)
        for button in (self.update_save_btn, self.update_check_btn, self.update_install_btn, self.update_release_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(0)
        self.update_progress.setVisible(False)
        layout.addWidget(self.update_progress)

        self.update_notes = QPlainTextEdit()
        self.update_notes.setReadOnly(True)
        self.update_notes.setPlaceholderText("As novidades da versão disponível aparecerão aqui.")
        self.update_notes.setMaximumBlockCount(300)
        self.update_notes.setMinimumHeight(130)
        layout.addWidget(self.update_notes, 1)

        policy = QLabel(
            "Instalação coordenada: após validar o pacote, o Sentinel fecha os streams e o banco, encerra a GUI, "
            "um helper externo aguarda até 10 s pelo processo e só então executa install.sh. O fluxo pós-update já "
            "existente reabre o aplicativo e mostra as novidades da nova versão."
        )
        policy.setWordWrap(True)
        policy.setStyleSheet("color:#809da8;font-size:11px")
        layout.addWidget(policy)
        self.config_tabs.addTab(tab, "Atualizações")

    @requires_permission('admin')
    def save_private_update_token(self):
        try:
            store_token(self.update_source_edit.text().strip(), self.update_private_token.text())
        except Exception as exc:
            QMessageBox.warning(self, "Acesso privado", f"Não foi possível guardar a chave de atualização.\n\n{exc}")
            return
        self.update_private_token.clear()
        self.update_status_label.setText("Chave privada guardada no cofre deste usuário para o endereço configurado.")

    def refresh_intelbras_netsdk_component_status(self):
        if not hasattr(self, "netsdk_component_status"):
            return
        info = intelbras_netsdk_runtime_info()
        ref = reference_audio_path()
        target = vendor_install_directory()
        if info.available:
            ref_text = "referência 05.Talk OK" if ref.is_file() else "referência 05.Talk ausente"
            self.netsdk_component_status.setText(
                f"NetSDK disponível • {info.architecture} • {ref_text}\n{target}"
            )
            self.netsdk_component_status.setStyleSheet("color:#79cfa5")
        else:
            self.netsdk_component_status.setText(
                f"NetSDK não instalado • {info.detail}\nSelecione o ZIP oficial da Intelbras uma única vez. Destino persistente: {target}"
            )
            self.netsdk_component_status.setStyleSheet("color:#e4c887")

    def import_intelbras_netsdk_ui(self):
        future = getattr(self, "netsdk_install_future", None)
        if future is not None and not future.done():
            return
        start_dir = os.path.expanduser("~/Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar NetSDK oficial Intelbras", start_dir,
            "Intelbras NetSDK (General_NetSDK_3.050_PlaySDK_3.042*.zip);;Arquivos ZIP (*.zip)"
        )
        if not path:
            return
        self.netsdk_component_status.setText("Importando NetSDK Intelbras em background…")
        self.netsdk_component_status.setStyleSheet("color:#98b3bc")
        self.netsdk_import_btn.setEnabled(False)
        self.netsdk_install_future = self.audio_executor.submit(
            install_from_official_archive, path, vendor_install_directory()
        )
        QTimer.singleShot(120, self._poll_intelbras_netsdk_install)

    def _poll_intelbras_netsdk_install(self):
        future = getattr(self, "netsdk_install_future", None)
        if future is None:
            return
        if not future.done():
            QTimer.singleShot(120, self._poll_intelbras_netsdk_install)
            return
        self.netsdk_install_future = None
        if hasattr(self, "netsdk_import_btn"):
            self.netsdk_import_btn.setEnabled(True)
        try:
            imported = future.result()
        except Exception as exc:
            self.refresh_intelbras_netsdk_component_status()
            QMessageBox.warning(self, "Intelbras NetSDK", f"Não foi possível importar o SDK oficial.\n\n{type(exc).__name__}: {exc}")
            return
        self.refresh_intelbras_netsdk_component_status()
        self.refresh_selected_audio_controls()
        QMessageBox.information(
            self, "Intelbras NetSDK",
            "Suporte Intelbras instalado para este usuário.\n\n"
            f"Arquivos importados: {', '.join(imported)}\n\n"
            "As próximas atualizações reutilizarão esta instalação local."
        )

    def _settings_from_update_ui(self) -> UpdateSettings:
        settings = self.update_settings
        settings.manifest_base_url = self.update_source_edit.text().strip()
        settings.channel = str(self.update_channel_combo.currentData() or "stable")
        settings.check_on_startup = bool(self.update_startup_check.isChecked())
        settings.require_signature = bool(self.update_require_signature.isChecked())
        return settings

    @requires_permission('admin')
    def save_update_ui_settings(self):
        self.update_settings = self._settings_from_update_ui()
        save_update_settings(data_dir(), self.update_settings)
        try:
            url = resolve_manifest_url(self.update_settings.manifest_base_url, self.update_settings.channel)
            self.update_status_label.setText(f"Configuração salva. Manifesto: {url}")
        except Exception as exc:
            self.update_status_label.setText(f"Configuração salva. {exc}")

    def _set_update_busy(self, busy: bool, text: str = ""):
        self.update_check_btn.setEnabled(not busy)
        self.update_save_btn.setEnabled(not busy)
        self.update_source_edit.setEnabled(not busy)
        self.update_channel_combo.setEnabled(not busy)
        self.update_startup_check.setEnabled(not busy)
        self.update_require_signature.setEnabled(not busy)
        self.update_install_btn.setEnabled((not busy) and bool(self.available_update and is_newer(self.available_update.version, __version__)))
        if text:
            self.update_status_label.setText(text)
        self.update_progress.setVisible(busy)
        if busy:
            self.update_progress.setRange(0, 0)
        else:
            self.update_progress.setRange(0, 100)
            self.update_progress.setValue(0)

    def check_for_updates_startup(self):
        if not authorize(self,'admin',notify=False):return
        settings = load_update_settings(data_dir())
        self.update_settings = settings
        if not should_check_on_startup(settings):
            return
        self.check_for_updates(True)

    def check_for_updates(self, silent: bool = False):
        if self.update_worker is not None:
            return
        if not silent:
            self.update_settings = self._settings_from_update_ui()
            save_update_settings(data_dir(), self.update_settings)
        settings = self.update_settings
        if not settings.manifest_base_url:
            if not silent:
                self.update_status_label.setText("Configure primeiro a fonte ArtinUpdates.")
                QMessageBox.information(
                    self, "Atualizações", "A fonte ArtinUpdates ainda não foi configurada.\n\n"
                    "Informe a URL base do manifesto na aba Atualizações."
                )
            return
        self._set_update_busy(True, "Verificando atualizações…")
        worker = Worker(
            fetch_update_manifest,
            settings.manifest_base_url,
            settings.channel,
            data_directory=data_dir(),
            require_signature=settings.require_signature,
        )
        self.update_worker = worker
        worker.signals.result.connect(lambda manifest, s=silent: self.update_check_result(manifest, s))
        worker.signals.error.connect(lambda error, s=silent: self.update_check_error(error, s))
        worker.signals.finished.connect(self._update_check_finished)
        self.start_qt_worker(worker)

    def _update_check_finished(self):
        self.update_worker = None
        self._set_update_busy(False)

    def update_check_result(self, manifest: UpdateManifest, silent: bool = False):
        self.available_update = manifest
        self.update_settings = mark_checked(data_dir(), self.update_settings, manifest.version)
        newer = is_newer(manifest.version, __version__)
        signature_text = ""
        if manifest.signature_value:
            signature_text = " • manifesto assinado"
        if newer:
            self.update_status_label.setText(
                f"Nova versão disponível: {manifest.version} — {manifest.title}{signature_text}"
            )
            self.update_install_btn.setEnabled(True)
            if not silent:
                QMessageBox.information(
                    self, "Atualização disponível",
                    f"Artin Sentinel {manifest.version} está disponível.\n\n{manifest.title}\n\n"
                    "Revise as novidades e use ‘Baixar e instalar’ quando desejar."
                )
            else:
                self.bottom_notice.setText(f"Atualização disponível: {manifest.version}")
        else:
            self.update_status_label.setText(f"Você já está na versão atual ({__version__}).")
            self.update_install_btn.setEnabled(False)
        self.update_release_btn.setEnabled(bool(manifest.release_url))
        notes = [f"{manifest.title}", f"Versão: {manifest.version} • Canal: {manifest.channel}"]
        if manifest.published_at:
            notes.append(f"Publicada em: {manifest.published_at}")
        notes.append("")
        notes.extend(f"• {item}" for item in manifest.notes)
        self.update_notes.setPlainText("\n".join(notes).strip())
        if self.akdb_sync_settings.check_with_app_updates:
            QTimer.singleShot(100, lambda: self.check_akdb_updates(True))

    def update_check_error(self, error: str, silent: bool = False):
        try:
            self.update_settings = mark_checked(data_dir(), self.update_settings)
        except Exception:
            pass
        self.update_status_label.setText(f"Não foi possível verificar agora: {error}")
        if not silent:
            QMessageBox.warning(self, "Atualizações", f"Não foi possível verificar atualizações.\n\n{error}")

    def open_update_release_page(self):
        manifest = self.available_update
        if manifest and manifest.release_url:
            QDesktopServices.openUrl(QUrl(manifest.release_url))

    def _update_progress_text(self, text: str):
        self.update_status_label.setText(text)
        import re
        match = re.search(r"(\d+)%", text or "")
        if match:
            self.update_progress.setRange(0, 100)
            self.update_progress.setValue(max(0, min(100, int(match.group(1)))))
        else:
            self.update_progress.setRange(0, 0)

    @requires_permission('admin')
    def download_and_install_update(self):
        manifest = self.available_update
        if not manifest or not is_newer(manifest.version, __version__):
            QMessageBox.information(self, "Atualizações", "Nenhuma versão mais nova está pronta para instalar.")
            return
        answer = QMessageBox.question(
            self,
            "Instalar atualização",
            f"Baixar, validar e instalar o Artin Sentinel {manifest.version}?\n\n"
            "O aplicativo será fechado após o pacote ser validado. Sites, layouts, banco local, AKDB e credenciais "
            "não são apagados pela atualização.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._set_update_busy(True, f"Preparando Artin Sentinel {manifest.version}…")
        self.update_install_btn.setEnabled(False)
        worker = Worker(
            stage_update,
            manifest,
            data_dir(),
            with_progress=True,
            require_signature=self.update_settings.require_signature,
            auth_base_url=self.update_settings.manifest_base_url,
        )
        self.update_install_worker = worker
        worker.signals.progress.connect(self._update_progress_text)
        worker.signals.result.connect(self.update_stage_ready)
        worker.signals.error.connect(self.update_stage_error)
        worker.signals.finished.connect(self._update_stage_finished)
        self.start_qt_worker(worker)

    def _update_stage_finished(self):
        self.update_install_worker = None
        if not self._update_in_progress:
            self._set_update_busy(False)

    def update_stage_error(self, error: str):
        self.update_status_label.setText(f"Atualização bloqueada: {error}")
        QMessageBox.critical(
            self, "Atualização não instalada",
            "O Sentinel não executou o instalador porque a validação do pacote falhou.\n\n" + error,
        )

    @requires_permission('admin')
    def update_stage_ready(self, staged: StagedUpdate):
        self.staged_update = staged
        others = other_sentinel_pids(os.getpid())
        if others:
            self._set_update_busy(False)
            self.update_status_label.setText("Instalação aguardando fechamento de outra instância do Sentinel")
            QMessageBox.warning(
                self, "Feche outras janelas",
                "Outro processo do Artin Sentinel ainda está aberto (PID: "
                + ", ".join(map(str, others)) + ").\n\n"
                "Feche todas as janelas do Sentinel e clique novamente em Instalar atualização. "
                "O pacote validado poderá ser baixado novamente, se necessário.",
            )
            return
        verification = "SHA-256 validado"
        if staged.signature_verified:
            verification += " • assinatura Ed25519 validada"
        self.update_status_label.setText(f"Pacote {staged.version} pronto — {verification}")
        answer = QMessageBox.question(
            self,
            "Atualização verificada",
            f"Artin Sentinel {staged.version} foi baixado e validado.\n\n{verification}.\n\n"
            "Feche outras instâncias do Sentinel, se houver. Esta janela será fechada automaticamente.\n\n"
            "Aplicar a atualização agora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            self._set_update_busy(False)
            self.update_status_label.setText(
                f"Pacote {staged.version} permanece verificado em cache. A instalação não foi iniciada."
            )
            return
        others = other_sentinel_pids(os.getpid())
        if others:
            self._set_update_busy(False)
            QMessageBox.warning(self, "Feche outras janelas",
                                "Outra instância do Sentinel continua aberta (PID: "
                                + ", ".join(map(str, others)) + "). Feche-a e tente novamente.")
            return
        try:
            launch_staged_update(staged, os.getpid())
        except Exception as exc:
            self._set_update_busy(False)
            QMessageBox.critical(self, "Atualizações", f"Não foi possível iniciar o helper de atualização.\n\n{exc}")
            return
        self._update_in_progress = True
        self.update_status_label.setText("Encerrando o Sentinel para aplicar a atualização…")
        self.bottom_notice.setText("Atualização validada — encerrando para instalar…")
        QTimer.singleShot(120, self.close)

    # ---------- refresh ----------
    def refresh_all(self):
        sites = self.db.list_sites()
        if self.current_site_id is None and sites:
            self.current_site_id = sites[0]["id"]

        self.site_table.setRowCount(len(sites))
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for row, site in enumerate(sites):
            self.site_combo.addItem(str(site["name"]), int(site["id"]))
            name_item = QTableWidgetItem(str(site["name"]))
            name_item.setData(Qt.UserRole, int(site["id"]))
            self.site_table.setItem(row, 0, name_item)
            self.site_table.setItem(row, 1, QTableWidgetItem(str(site["description"])))
            if int(site["id"]) == int(self.current_site_id or -1):
                self.site_table.selectRow(row)
        selected_site_index = self.site_combo.findData(int(self.current_site_id or -1))
        self.site_combo.setCurrentIndex(selected_site_index)
        self.site_combo.blockSignals(False)
        self.site_count_label.setText(f"{len(sites)} Site(s) • cada equipamento em um Site")
        self.refresh_playback_access()

        devices = self.db.list_devices(self.current_site_id)
        self.dev_table.setRowCount(len(devices))
        online = offline = attentions = 0
        for row, device in enumerate(devices):
            model = clean_model(device["manufacturer"], device["model"])
            maker_model = " / ".join(part for part in (device["manufacturer"] or "", "" if model == "—" else model) if part) or "—"
            channel_rows = self.db.list_recorder_channels(device["id"])
            video_count = sum(bool(ch["available"]) for ch in channel_rows)
            profile_key = self._selected_device_profile_key(device)
            caps = capability_map(provider=str(device["provider"] or ""), profile_key=profile_key)
            known_capacity = int(caps.get("max_total_channels") or 0)
            channels_text = (f"✓ {len(channel_rows)}/{known_capacity} lidos" if channel_rows and known_capacity >= len(channel_rows)
                             else f"✓ {len(channel_rows)} lidos" if channel_rows else "Pendente")
            channels_detail = (f"Rastreado: {len(channel_rows)} canal(is) salvo(s)"
                               + (f" de {known_capacity} posições previstas" if known_capacity >= len(channel_rows) else "")
                               + f" • {video_count} com vídeo confirmado" if channel_rows else
                               "Canais ainda não rastreados neste cadastro.")
            audio_modes = [channel_audio_info(device, ch) for ch in channel_rows]
            if any(info["can_talk"] for info in audio_modes):
                audio_state = "Bidirecional"
            elif any(info["can_listen"] for info in audio_modes):
                pending_talk = any(info["mode"] == "bidirectional" for info in audio_modes)
                audio_state = "Escuta • retorno pendente" if pending_talk else "Escuta"
            else:
                known_audio = audio_capability(provider=device["provider"])
                known_mode = known_audio.get("mode")
                known_protocol = str(known_audio.get("talkback_protocol") or "")
                if known_mode == "bidirectional":
                    audio_state = "Escuta • retorno pendente" if known_protocol in {"", "unvalidated", "candidate"} else "Bidirecional"
                else:
                    audio_state = "Escuta" if known_mode == "listen" else "—"
            endpoints = self.db.list_device_endpoints(int(device["id"]))
            endpoint_ips = [str(ep["ip"]) for ep in endpoints if str(ep["ip"] or "")]
            ip_text = device["ip"]
            if len(endpoint_ips) > 1:
                ip_text = f"{device['ip']} +{len(endpoint_ips) - 1}"
            values = (
                device_visual_name(device),
                ip_text,
                resolve_operational_identity(device).kind_label,
                maker_model,
                device["status"],
                channels_text,
                audio_state,
                f"{int(device['identity_confidence'] or 0)}%" if int(device['identity_confidence'] or 0) else "—",
                "salva" if device["credential_saved"] else "—",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.UserRole, int(device["id"]))
                    item.setToolTip(f"Provider: {device['provider']} • ID local: {device['id']}")
                elif col == 1 and endpoints:
                    item.setToolTip("Endpoints do mesmo equipamento:\n" + "\n".join(
                        f"{ep['ip']} • {status_label(ep['status'])}" for ep in endpoints
                    ))
                elif col == 4:
                    item.setIcon(status_dot_icon(str(device["status"] or "unknown"), 8))
                elif col == 5:
                    item.setToolTip(channels_detail + "\nUse Canais / Stream para atualizar a leitura.")
                self.dev_table.setItem(row, col, item)
            online += device["status"] == "online"
            offline += device["status"] == "offline"
            attentions += device["status"] == "offline"

        if hasattr(self, "device_inventory_count"):
            self._device_inventory_online_count = online
            self.device_inventory_count.setText(f"{len(devices)} cadastrado(s) • {online} online")

        if hasattr(self, "device_filter"):
            self.refresh_device_filter(self.device_filter.text())
        if hasattr(self, "device_detail_name"):
            self.refresh_device_inspector()

        site = next((s for s in sites if s["id"] == self.current_site_id), None)
        site_name = site["name"] if site else "—"
        unknown = len(devices) - online - offline
        self.top_site_label.setText(f"Site: {site_name}")
        self.live_health.setText(
            f"{site_name} · {len(devices)} equipamentos · {online} online"
            + (f" · {offline} offline" if offline else "")
            + (f" · {unknown} sem estado" if unknown else "")
        )
        health_rows = self.db.channel_health_summary(self.current_site_id)
        active_rows = [row for row in health_rows if str(row["device_status"] or "") == "online"]
        channel_ok = sum(str(row["health_state"] or "unknown") == "ok" for row in active_rows)
        channel_problem = sum(str(row["health_state"] or "unknown") in {"offline", "no_signal"} for row in active_rows)
        channel_degraded = sum(str(row["health_state"] or "unknown") == "degraded" for row in active_rows)
        channel_unverified = sum(str(row["health_state"] or "unknown") == "unverified" for row in active_rows)
        channel_unknown = len(active_rows) - channel_ok - channel_problem - channel_degraded - channel_unverified
        self.health_label.setText(
            f"SITE — {site_name}\n\n"
            f"Equipamentos: {len(devices)} • Online: {online} • Offline: {offline} • Sem estado: {unknown}\n"
            f"Canais inventariados: {len(health_rows)} • OK: {channel_ok} • Problema: {channel_problem} • "
            f"Em confirmação: {channel_degraded} • Inconclusivo: {channel_unverified} • Sem estado: {channel_unknown}"
            f" • Equip. offline: {len(health_rows) - len(active_rows)}\n\n"
            "Quando o DVR/NVR fornece estado nativo, o Sentinel diferencia perda de sinal analógico de câmera IP offline. "
            "Falhas RTSP sem telemetria nativa ficam inconclusivas; não comprovam perda de sinal."
        )
        if hasattr(self, "channel_health_table"):
            self.channel_health_table.setRowCount(len(health_rows))
            for r, ch in enumerate(health_rows):
                state = (str(ch["health_state"] or "unknown") if str(ch["device_status"] or "") == "online"
                         else "device_offline")
                kind = str(ch["channel_kind"] or "unknown")
                type_label = "IP / proxy" if kind == "ip" else ("Analógico" if kind == "analog" else "—")
                endpoint = str(ch["source_ip"] or "")
                if endpoint and int(ch["source_port"] or 0):
                    endpoint = f"{endpoint}:{int(ch['source_port'])}"
                vals = (
                    ch["device_name"] or "—", self.db.channel_display_name(ch),
                    channel_health_label(ch, device_online=state != "device_offline"),
                    type_label, endpoint or "—", ch["source_protocol"] or "—",
                    ch["health_last_change_at"] or "—",
                    ("Equipamento offline; canal não verificado agora" if state == "device_offline" else ch["health_detail"] or "—"),
                )
                for c, value in enumerate(vals):
                    item = QTableWidgetItem(str(value))
                    if c == 2:
                        icon_state = "online" if state == "ok" else ("offline" if state in {"offline", "no_signal"} else "unknown")
                        item.setIcon(status_dot_icon(icon_state, 7))
                    self.channel_health_table.setItem(r, c, item)
        total_attentions = attentions + channel_problem
        self.bottom_right.setText(
            (f"{total_attentions} atenção(ões) • " if total_attentions else "") + "Monitoramento: 30 s"
        )

        events = self.db.list_events()
        self.event_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (event["created_at"], event["severity"], event["event_type"], event["device_name"] or "—", history_message(event))
            for col, value in enumerate(values):
                self.event_table.setItem(row, col, QTableWidgetItem(str(value)))
        if events:
            latest = events[0]
            self.live_activity.setText(f"{latest['created_at']}\n{latest['message']}")
        else:
            self.live_activity.setText("Nenhum evento registrado.")

        self.refresh_source_tree(sites, self.db.list_devices(None))
        if hasattr(self, "devices_found_table") and self.devices_found_table.rowCount() == len(self.discovery_results):
            self.refresh_discovery_registration()

    # ---------- site / device management ----------
    @requires_permission('admin')
    def add_site(self):
        name, ok = QInputDialog.getText(self, "Novo Site", "Nome do Site:")
        if ok and name.strip():
            try:
                self.save_live_workspace()
                self.current_site_id = self.db.add_site(name.strip())
                self.discovery_web_results = {}
                self._transient_web_checks = {}
                self.discovery_results = []
                self.devices_found_table.setRowCount(0)
                self.refresh_all()
                self.restore_live_workspace()
            except Exception as exc:
                QMessageBox.warning(self, "Site", str(exc))

    def selected_site_id(self):
        row = self.site_table.currentRow()
        if row >= 0 and self.site_table.item(row, 0):
            value = self.site_table.item(row, 0).data(Qt.UserRole)
            if value is not None:
                return int(value)
        return int(self.current_site_id) if self.current_site_id is not None else None

    def select_site_from_table(self, row, _col):
        try:
            item = self.site_table.item(row, 0)
            site_id = int(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) is not None else None
            if site_id is None:
                return
            self.activate_site(site_id)
        except Exception:
            pass

    def select_site_from_combo(self, _index):
        site_id = self.site_combo.currentData()
        if site_id is not None:
            self.activate_site(int(site_id))

    def activate_site(self, site_id: int):
        if self.current_site_id == site_id:
            return
        self.save_live_workspace()
        self.current_site_id = site_id
        self.discovery_web_results = {}
        self._transient_web_checks = {}
        self.discovery_results = []
        self.devices_found_table.setRowCount(0)
        self.devices_found_status.setText("Site alterado; busque equipamentos nesta rede.")
        self.refresh_all()
        self.restore_live_workspace()

    def show_site_context_menu(self, pos):
        index = self.site_table.indexAt(pos)
        if not index.isValid():
            return
        self.site_table.selectRow(index.row())
        menu = QMenu(self)
        rename = menu.addAction("Renomear")
        rename.triggered.connect(self.rename_selected_site)
        archive = menu.addAction("Arquivar Site")
        archive.triggered.connect(self.archive_selected_site)
        menu.addSeparator()
        delete = menu.addAction("Excluir Site…")
        delete.triggered.connect(self.delete_selected_site)
        menu.popup(self.site_table.viewport().mapToGlobal(pos))
        self._site_context_menu = menu

    @requires_permission('admin')
    def rename_selected_site(self):
        site_id = self.selected_site_id()
        if site_id is None:
            QMessageBox.information(self, "Site", "Selecione um Site.")
            return
        site = self.db.get_site(site_id)
        if not site:
            return
        name, ok = QInputDialog.getText(self, "Renomear Site", "Nome do Site:", text=site["name"])
        if not ok or not name.strip():
            return
        try:
            self.db.update_site(site_id, name.strip(), site["description"] or "")
        except Exception as exc:
            QMessageBox.warning(self, "Site", str(exc))
            return
        self.refresh_all()

    def _stop_site_live_sessions(self, site_id: int):
        for device in self.db.list_devices(site_id, include_archived=True):
            self._stop_device_live_sessions(int(device["id"]))

    @requires_permission('admin')
    def archive_selected_site(self):
        site_id = self.selected_site_id()
        if site_id is None:
            return
        active = self.db.list_sites()
        if len(active) <= 1:
            QMessageBox.information(
                self, "Arquivar Site",
                "Este é o único Site ativo. Crie outro Site antes de arquivá-lo.",
            )
            return
        site = self.db.get_site(site_id)
        answer = QMessageBox.question(
            self, "Arquivar Site",
            f"Arquivar '{site['name']}' e removê-lo da operação ativa?\n\n"
            "Equipamentos, canais, histórico e credenciais serão preservados.",
        )
        if answer != QMessageBox.Yes:
            return
        self._stop_site_live_sessions(site_id)
        self.db.archive_site(site_id, True)
        remaining = [s for s in self.db.list_sites() if int(s["id"]) != site_id]
        self.current_site_id = int(remaining[0]["id"]) if remaining else None
        self.refresh_all()
        self.restore_live_workspace()

    @requires_permission('admin')
    def show_archived_sites(self):
        rows = self.db.list_archived_sites()
        if not rows:
            QMessageBox.information(self, "Sites arquivados", "Não há Sites arquivados.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Sites arquivados")
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Site", "Descrição"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for r, site in enumerate(rows):
            item = QTableWidgetItem(site["name"])
            item.setData(Qt.UserRole, int(site["id"]))
            table.setItem(r, 0, item)
            table.setItem(r, 1, QTableWidgetItem(site["description"] or ""))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        restore = QPushButton("Restaurar")
        buttons.addButton(restore, QDialogButtonBox.ActionRole)
        def restore_selected():
            if not authorize(self,'admin'):return
            row = table.currentRow()
            if row < 0 or not table.item(row, 0):
                return
            restore_id = int(table.item(row, 0).data(Qt.UserRole))
            self.db.archive_site(restore_id, False)
            self.current_site_id = restore_id
            self.refresh_all()
            dialog.accept()
        restore.clicked.connect(restore_selected)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(640, 360)
        self._transient_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0, d=dialog: self._release_transient_dialog(d))
        dialog.open()

    @requires_permission('admin')
    def delete_selected_site(self):
        site_id = self.selected_site_id()
        if site_id is None:
            return
        site = self.db.get_site(site_id)
        if not site:
            return
        devices = self.db.list_devices(site_id, include_archived=True)
        other_sites = [s for s in self.db.list_sites() if int(s["id"]) != int(site_id)]

        if not devices:
            answer = QMessageBox.warning(
                self, "Excluir Site",
                f"Excluir permanentemente o Site '{site['name']}'?\n\nO layout deste Site também será removido.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self.db.delete_site_permanently(site_id)
        else:
            dialog = QDialog(self)
            dialog.setWindowTitle("Excluir Site")
            form = QFormLayout(dialog)
            warning = QLabel(
                f"O Site '{site['name']}' possui {len(devices)} equipamento(s).\n"
                "Escolha o que fazer com eles antes de excluir o Site."
            )
            warning.setWordWrap(True)
            form.addRow(warning)
            action = QComboBox()
            if other_sites:
                action.addItem("Mover equipamentos para outro Site", "move")
            action.addItem("Excluir Site e todos os equipamentos", "delete")
            target = QComboBox()
            for target_site in other_sites:
                target.addItem(target_site["name"], int(target_site["id"]))
            target.setEnabled(bool(other_sites))
            form.addRow("Ação", action)
            form.addRow("Site de destino", target)
            note = QLabel("A exclusão conjunta remove canais, layout e credenciais salvas somente dos equipamentos deste Site.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#a6bec4")
            form.addRow(note)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText("Continuar")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            def sync_target(_=0):
                target.setEnabled(action.currentData() == "move")
            action.currentIndexChanged.connect(sync_target)
            sync_target()
            if dialog.exec() != QDialog.Accepted:
                return
            mode = action.currentData()
            if mode == "move":
                target_id = target.currentData()
                if target_id is None:
                    QMessageBox.warning(self, "Excluir Site", "Selecione um Site de destino.")
                    return
                self._stop_site_live_sessions(site_id)
                try:
                    self.db.delete_site_permanently(site_id, target_site_id=int(target_id))
                except Exception as exc:
                    QMessageBox.warning(self, "Excluir Site", str(exc))
                    return
                self.current_site_id = int(target_id)
            else:
                confirm = QMessageBox.warning(
                    self, "Excluir Site e equipamentos",
                    f"Excluir permanentemente '{site['name']}' e seus {len(devices)} equipamento(s)?\n\n"
                    "Esta ação remove canais, layouts, histórico e credenciais associadas somente a este Site.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if confirm != QMessageBox.Yes:
                    return
                self._stop_site_live_sessions(site_id)
                for device in devices:
                    try:
                        self.credential_store.delete_password(int(device["id"]))
                    except Exception:
                        pass
                    self.session_credentials.pop(int(device["id"]), None)
                self.db.delete_site_permanently(site_id, delete_devices=True)

        remaining = self.db.list_sites()
        if not remaining:
            try:
                self.current_site_id = self.db.add_site("Local", "Site padrão")
            except Exception:
                all_sites = self.db.list_sites(include_archived=True)
                if all_sites:
                    self.db.archive_site(int(all_sites[0]["id"]), False)
                    self.current_site_id = int(all_sites[0]["id"])
        elif self.current_site_id == site_id or self.current_site_id is None:
            self.current_site_id = int(remaining[0]["id"])
        self.refresh_all()
        self.restore_live_workspace()

    @requires_permission('device_add')
    def add_intelbras_cloud_bridge(self):
        from .intelbras_cloud_ui import open_bridge_dialog
        open_bridge_dialog(self)

    @requires_permission('device_edit')
    def configure_intelbras_cloud_bridge(self, device):
        from .intelbras_cloud_ui import open_bridge_dialog
        open_bridge_dialog(self, device)

    @requires_permission('device_add')
    def add_device_manual(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Adicionar equipamento")
        form = QFormLayout(dialog)
        name, ip, web, rtsp = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        manufacturer,model=QLineEdit(),QLineEdit()
        for field,key in ((name,'deviceName'),(ip,'deviceHost'),(web,'deviceWeb'),(rtsp,'deviceRtsp'),(manufacturer,'deviceBrand'),(model,'deviceModel')):field.setObjectName(key)
        access = QComboBox()
        access.addItem("Rede local", ACCESS_LOCAL)
        access.addItem("Outro local • rede privada/VPN", ACCESS_PRIVATE)
        access.addItem("Outro local • conector por Site (piloto)", ACCESS_CONNECTOR)
        access_help = QLabel()
        access_help.setWordWrap(True)
        access_help.setStyleSheet("color:#a6bec4;font-size:10px")
        def update_access_help():
            if access.currentData() == ACCESS_PRIVATE:
                access_help.setText(
                    "Use o IPv4 ou nome do gravador alcançável pela rede privada. "
                    "A VPN deve estar conectada antes do diagnóstico e da leitura dos canais. "
                    "O código/serial da nuvem do fabricante ainda não é um endereço de vídeo."
                )
                ip.setPlaceholderText("Ex.: 10.20.30.40 ou gravador.exemplo.interno")
            elif access.currentData() == ACCESS_CONNECTOR:
                access_help.setText(
                    "Abra o túnel do operador antes de ler canais. Cadastre IP/host 127.0.0.1, "
                    "Web URL http://127.0.0.1:18080 e RTSP URL rtsp://127.0.0.1:18554. "
                    "Use um par de portas diferente para cada Site. O serial Cloud não é necessário."
                )
                ip.setPlaceholderText("127.0.0.1")
            else:
                access_help.setText("Equipamento na rede local deste computador.")
                ip.setPlaceholderText("IPv4 ou nome do equipamento")
        access.currentIndexChanged.connect(update_access_help)
        update_access_help()
        kind = QComboBox()
        kind.addItem("Não identificado", "unknown")
        kind.addItem("Câmera IP", "camera")
        kind.addItem("DVR", "dvr")
        kind.addItem("NVR", "nvr")
        kind.addItem("DVR / Multi HD", "xvr")
        protocol = QComboBox()
        protocol.addItem("Automático (identidade conhecida)", "")
        protocol.addItem("Intelbras / Dahua (protocolo compatível)", "intelbras")
        protocol.addItem("Hikvision / JFL (protocolo compatível)", "hikvision")
        from .access_policy import recommendation
        access_recommendation=QLabel();access_recommendation.setWordWrap(True)
        sdk_auto=QCheckBox('Preparar acesso SDK local compatível (se disponível)');sdk_auto.setChecked(True)
        suggested_provider=[None]
        def suggest_access():
            from .hik_sdk import runtime_dir
            try:runtime_dir();available=True
            except ValueError:available=False
            hint=recommendation(manufacturer.text(),kind.currentData(),available)
            if protocol.currentData() in ('',suggested_provider[0]):
                protocol.setCurrentIndex(max(0,protocol.findData(hint['provider'])))
                suggested_provider[0]=hint['provider']
            access_recommendation.setText(hint['detail'])
            sdk_auto.setVisible(hint['sdk']=='hikvision');sdk_auto.setEnabled(available)
        manufacturer.textChanged.connect(suggest_access);kind.currentIndexChanged.connect(suggest_access)
        suggest_access()
        for label, widget in [("Marca",manufacturer),("Modelo",model),("",access_recommendation),("",sdk_auto),("Acesso", access), ("", access_help), ("Nome", name), ("IP/host", ip), ("Tipo", kind), ("Protocolo do gravador", protocol), ("Web URL", web), ("RTSP URL", rtsp)]:
            form.addRow(label, widget)
        from .registration_assist import add_reference_picker
        reference_picker=add_reference_picker(form,dialog,manufacturer,model,kind,protocol)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        host = web_url = rtsp_url = ""
        def validate_and_accept():
            nonlocal host, web_url, rtsp_url
            field = ip
            try:
                host = validate_recorder_host(ip.text())
                field = web
                web_url = validate_endpoint_url(web.text(), schemes=("http", "https"))
                field = rtsp
                rtsp_url = validate_endpoint_url(rtsp.text(), schemes=("rtsp", "rtsps"))
            except ValueError as exc:
                QMessageBox.warning(dialog, "Endereço do equipamento", str(exc))
                field.setFocus()
                field.selectAll()
                return
            dialog.accept()
        buttons.accepted.connect(validate_and_accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            try:
                device_kind = DeviceKind(kind.currentData())
            except Exception:
                device_kind = DeviceKind.UNKNOWN
            device = Device(
                site_id=self.current_site_id,
                name=name.text().strip() or host,
                ip=host,
                kind=device_kind,
                manufacturer=manufacturer.text().strip(),model=model.text().strip(),
                web_url=web_url,
                rtsp_url=rtsp_url,
                metadata={"connection_mode": access.currentData(), "recorder_protocol": protocol.currentData(),"manual_akdb_reference":reference_picker.state["applied"]},
            )
            # Only a new, explicitly Hikvision recorder is prepared. Never migrate an existing unit silently.
            from .access_policy import recommendation
            hint=recommendation(manufacturer.text(),kind.currentData(),sdk_auto.isEnabled())
            existing=self.db.find_device_by_site_ip(self.current_site_id,host)
            if existing is None and hint['sdk']=='hikvision' and sdk_auto.isEnabled() and sdk_auto.isChecked():
                device.metadata['hik_sdk']={'enabled':False,'live':False,'port':8000,'channels':{}}
                device.metadata['access_setup_note']='SDK preparado; confirme o mapa de canais antes do uso.' 
            if existing is not None and not authorize(self,'device_edit'):return
            device_id = self.db.upsert_device(device)
            # Explicit manual inclusion also means "restore" for a matching
            # archived record. upsert preserves archived by design.
            saved = self.db.get_device(device_id)
            if saved and saved["archived"]:
                self.db.archive_device(device_id, False)
                self.db.set_ignore_discovery(device_id, False)
            # A type chosen in manual onboarding is an operator decision and must
            # survive later discovery/ONVIF classification.
            if device_kind != DeviceKind.UNKNOWN:
                self.db.update_device_identity(
                    device_id, device.name, str(device_kind), device.manufacturer, device.model
                )
            self.refresh_all()
            if existing is None and hint['sdk']=='hikvision' and sdk_auto.isEnabled() and sdk_auto.isChecked():
                from .hik_sdk_ui import configure
                configure(self,device_id=device_id,prefer_sdk=True)

    def selected_device_id(self):
        row = self.dev_table.currentRow()
        if row >= 0 and self.dev_table.item(row, 0):
            value = self.dev_table.item(row, 0).data(Qt.UserRole)
            if value is not None:
                return int(value)
        return None

    def _device_selection_changed(self):
        self._sync_selected_device_actions()
        self.refresh_device_inspector()

    def refresh_device_filter(self, text=""):
        if not hasattr(self, "dev_table"):
            return
        query = (text if isinstance(text, str) else "").strip().casefold()
        visible = 0
        for row in range(self.dev_table.rowCount()):
            haystack = " ".join(
                (self.dev_table.item(row, col).text() if self.dev_table.item(row, col) else "")
                for col in range(self.dev_table.columnCount())
            ).casefold()
            hidden = bool(query and query not in haystack)
            self.dev_table.setRowHidden(row, hidden)
            visible += not hidden
        if hasattr(self, "device_inventory_count") and hasattr(self, "_device_inventory_online_count"):
            if query:
                self.device_inventory_count.setText(
                    f"{visible} de {self.dev_table.rowCount()} exibidos • "
                    f"{self._device_inventory_online_count} online"
                )
            else:
                self.device_inventory_count.setText(
                    f"{self.dev_table.rowCount()} cadastrado(s) • "
                    f"{self._device_inventory_online_count} online"
                )

    def _selected_device_profile_key(self, device) -> str:
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        ports = metadata.get("open_ports") or [] if isinstance(metadata, dict) else []
        stored_key = str(metadata.get("akdb_profile") or "") if isinstance(metadata, dict) else ""
        # Manual model/fabricante data can resolve a model-specific AKDB profile
        # even before a fresh network discovery has rewritten metadata. Prefer a
        # strong concrete match over a stale generic provider-wide profile.
        text = " ".join(
            str(device[name] or "") for name in ("manufacturer", "model", "detected_manufacturer", "detected_model", "name")
            if name in device.keys()
        )
        provider_name = str(device["provider"] or "")
        reconciled = reconcile_operational_profile_key(
            profile_key=stored_key, provider=provider_name, identity_text=text
        )
        if reconciled and reconciled != stored_key:
            return reconciled
        match = best_profile(text=text, ports=ports, manufacturer=str(device["manufacturer"] or ""))
        if match and match[0] >= 80 and match[1].family:
            return reconcile_operational_profile_key(
                profile_key=match[1].key, provider=provider_name, identity_text=text
            )
        # A vendor-only weak match (e.g. generic Intelbras -> Mibo) must not
        # select a model-specific capability or silently cap a recorder.
        return reconciled

    def refresh_device_inspector(self):
        if not hasattr(self, "device_detail_name"):
            return
        device_id = self.selected_device_id()
        if hasattr(self,'hik_sdk_button'):
            device=self.db.get_device(device_id) if device_id else None
            self.hik_sdk_button.setVisible(bool(device and uses_hikvision_recordings(device)))
        if not device_id:
            self.device_detail_name.setText("Selecione um equipamento")
            if hasattr(self,'device_detail_evidence'):self.device_detail_evidence.clear()
            self.device_detail_identity.setText("Identidade e endereço aparecerão aqui.")
            self.device_detail_capabilities.setText("—")
            self.device_detail_protocols.setText("—")
            self.device_live_btn.setEnabled(False)
            self.device_details_channels_btn.setEnabled(False)
            return
        device = self.db.get_device(device_id)
        if not device:
            return
        profile_key = self._selected_device_profile_key(device)
        caps = capability_map(provider=str(device["provider"] or ""), profile_key=profile_key)
        model = clean_model(device["manufacturer"], device["model"])
        identity = " / ".join(part for part in (device["manufacturer"] or "", "" if model == "—" else model) if part) or "Identidade não confirmada"
        state = str(device["status"] or "unknown")
        state_label = {"online": "● Online", "offline": "● Offline", "unknown": "○ Estado desconhecido"}.get(state, state)
        self.device_detail_name.setText(device_visual_name(device))
        from .registration_assist import evidence_summary
        try: identity_metadata=json.loads(device['metadata_json'] or '{}')
        except (ValueError,TypeError): identity_metadata={}
        self.device_detail_name.setToolTip(evidence_summary(identity_metadata))
        if hasattr(self,'device_detail_evidence'):
            self.device_detail_evidence.setText(evidence_summary(identity_metadata))
        confidence = int(device["identity_confidence"] or 0)
        confidence_text = f"{confidence}%" if confidence else "—"
        operational = resolve_operational_identity(device)
        detected_kind = str(device["detected_kind"] or "unknown") if "detected_kind" in device.keys() else str(device["kind"] or "unknown")
        route_line = routing_explanation(operational)
        detected_line = f"Detectado: {friendly_kind(detected_kind)}"
        if operational.source.startswith("operator"):
            detected_line += " • override manual ativo"
        endpoints = self.db.list_device_endpoints(int(device_id))
        endpoint_parts = []
        for ep in endpoints:
            roles = []
            if ep["web_url"]:
                roles.append("Web")
            if ep["rtsp_url"]:
                roles.append("RTSP")
            if ep["onvif_url"]:
                roles.append("ONVIF")
            role_text = "/".join(roles) if roles else "rede"
            primary = " • principal" if ep["is_primary"] else ""
            endpoint_parts.append(f"{ep['ip']} ({role_text}{primary})")
        endpoint_line = " • ".join(endpoint_parts) if endpoint_parts else str(device["ip"])
        canonical = str(device["canonical_type"] or "unknown") if "canonical_type" in device.keys() else "unknown"
        subtype = str(device["device_subtype"] or "") if "device_subtype" in device.keys() else ""
        homologation = str(device["homologation_status"] or "unknown") if "homologation_status" in device.keys() else "unknown"
        akdb_id = str(device["akdb_stable_id"] or "") if "akdb_stable_id" in device.keys() else ""
        fingerprint_conf = int(device["fingerprint_confidence"] or 0) if "fingerprint_confidence" in device.keys() else 0
        type_line = canonical_type_label(canonical) + (f" • {subtype}" if subtype else "")
        akdb_display = profile_key or akdb_id or "sem match"
        akdb_line = f"AKDB: {akdb_display} • {fingerprint_conf or confidence}% • {homologation}"
        self.device_detail_identity.setText(
            f"{operational.kind_label} • {identity}\n"
            f"{type_line}\n"
            f"{state_label} • MAC {device['mac'] or 'não confirmado'}\n"
            f"Endpoints: {endpoint_line}\n"
            f"{access_label(json.loads(device['metadata_json'] or '{}'))}\n"
            f"Provider: {device['provider'] or 'generic'} • Confiança operacional: {confidence_text}\n"
            f"{akdb_line}\nRoteamento: {route_line}\n{detected_line}"
        )
        capability_lines = []
        features = list(caps.get("features") or [])
        if caps.get("stream_count"):
            capability_lines.append(f"Streams: {caps['stream_count']}")
        if caps.get("video_codecs"):
            capability_lines.append("Vídeo: " + ", ".join(caps["video_codecs"]))
        if caps.get("onvif_profiles"):
            capability_lines.append("ONVIF: Profile " + "/".join(caps["onvif_profiles"]))
        ptz = caps.get("ptz") or {}
        ptz_mode = str(ptz.get("mode") or "unknown")
        capability_lines.append("PTZ: " + (ptz_mode if ptz_mode not in {"", "unknown", "none"} else "não confirmado" if ptz_mode != "none" else "não suportado"))
        audio = caps.get("audio") or {}
        audio_mode = str(audio.get("mode") or "unknown")
        capability_lines.append("Áudio: " + ({"none": "não suportado", "listen": "escuta", "bidirectional": "bidirecional"}.get(audio_mode, "não confirmado")))
        total = int(caps.get("max_total_channels") or 0)
        if total:
            analog = int(caps.get("max_analog_channels") or 0)
            ip = int(caps.get("max_ip_channels") or 0)
            detail = f" ({analog} analógicos + {ip} IP)" if analog or ip else " (tipo das entradas ainda não confirmado)"
            capability_lines.append(f"Canais: até {total}{detail}")
        if features:
            capability_lines.append("Recursos: " + ", ".join(features))
        if not capability_lines:
            capability_lines.append("Capacidades ainda não mapeadas para este modelo.")
        self.device_detail_capabilities.setText("\n".join(capability_lines))
        protocols = list(caps.get("native_protocols") or [])
        protocol_text = " • ".join(protocols) if protocols else "Somente protocolos detectados dinamicamente."
        if profile_key:
            protocol_text += f"\nAKDB: {profile_key} • {caps.get('validation') or 'detected'}"
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        http_api = metadata.get("intelbras_http_api") if isinstance(metadata, dict) else None
        if isinstance(http_api, dict):
            if http_api.get("supported"):
                api_bits = ["Intelbras HTTP API"]
                if http_api.get("api_version"):
                    api_bits.append(f"v{http_api['api_version']}")
                if http_api.get("audio_inputs") is not None:
                    api_bits.append(f"áudio IN {http_api['audio_inputs']}")
                if http_api.get("audio_outputs") is not None:
                    api_bits.append(f"áudio OUT {http_api['audio_outputs']}")
                if http_api.get("post_audio_candidate"):
                    api_bits.append("postAudio candidato")
                protocol_text += "\n" + " • ".join(api_bits)
            elif http_api.get("detail"):
                protocol_text += "\nIntelbras HTTP API: " + str(http_api.get("detail"))
        self.device_detail_protocols.setText(protocol_text)
        self.device_live_btn.setEnabled(bool(self.db.list_recorder_channels(device_id)))
        self.device_details_channels_btn.setEnabled(True)

    def open_selected_device_in_live_view(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        channels = self.db.list_recorder_channels(device_id)
        if not channels:
            QMessageBox.information(self, "Live View", "Este equipamento ainda não possui canal/stream validado. Use Canais / Stream primeiro.")
            return
        self.show_page(self.PAGE_LIVE)
        self.open_all_device_channels(device_id)

    @requires_permission("device_edit")
    def configure_hik_sdk(self):
        from .hik_sdk_ui import configure
        configure(self)

    def _sync_selected_device_actions(self):
        device_id = self.selected_device_id()
        services = self._device_web_services(device_id) if device_id else []
        web_ok = bool(services)
        if hasattr(self, "web_button"):
            self.web_button.setEnabled(web_ok)
            self.web_button.setToolTip(
                "Confirmação histórica: a última tentativa falhou. Abrir no navegador padrão."
                if services and services[0]["last_outcome"] != "confirmed"
                else "Abrir serviço HTTP/HTTPS confirmado no navegador padrão."
            )
        if hasattr(self, "playback_web_button"):
            playback_id = self.playback_device_combo.currentData()
            self.playback_web_button.setEnabled(bool(playback_id is not None and self._device_web_services(playback_id)))

    def _device_web_services(self, device_id):
        device = self.db.get_device(device_id)
        if not device or device["site_id"] != self.current_site_id:
            return []
        metadata = json.loads(device["metadata_json"] or "{}")
        services = []
        cache = getattr(self, "_transient_web_checks", {})
        # The storage API also includes historical endpoints of correlated rows.
        for row in self.db.list_device_web_services(device_id):
            try:
                if (not is_transient_web_endpoint(row["endpoint_ip"], metadata)
                        and (self.current_site_id, device_id, row["endpoint_ip"]) not in cache):
                    services.append(row)
            except ValueError:
                continue
        for endpoint in self.db.list_device_endpoints(device_id):
            try:
                transient = is_transient_web_endpoint(endpoint["ip"], metadata)
            except ValueError:
                continue
            key = (self.current_site_id, device_id, endpoint["ip"])
            if transient or key in cache:
                checks = cache.get(key, [])
                services.extend(web_services_from_checks(checks, is_primary=endpoint["is_primary"], endpoint_ip=endpoint["ip"]))
        return ordered_web_services(services)

    def _remember_discovered_web_checks(self, device_id, device, checks, *, confirmed_only=False):
        if not checks:
            return
        owner = self.db.get_device(device_id)
        if not owner or owner["site_id"] != self.current_site_id or device.site_id != self.current_site_id:
            return
        metadata = json.loads(owner["metadata_json"] or "{}")
        if (is_transient_web_endpoint(device.ip, metadata)
                or is_transient_web_endpoint(device.ip, device.metadata)):
            if not hasattr(self, "_transient_web_checks"):
                self._transient_web_checks = {}
            self._transient_web_checks[(self.current_site_id, device_id, device.ip)] = list(checks)
        else:
            persist_discovered_web_checks(self.db, device_id, device, checks, confirmed_only=confirmed_only)

    def _open_web_services(self, services, still_current):
        services = ordered_web_services(services)
        if not services:
            QMessageBox.information(self, "Interface Web", "Nenhum serviço HTTP/HTTPS confirmado para este equipamento.")
            return
        selected = services[0]
        if len(services) > 1:
            labels = []
            for service in services:
                state = ("Confirmação atual" if service["last_outcome"] == "confirmed"
                         else "Confirmação histórica • falha recente")
                if service["scheme"] == "https" and service.get("last_tls_status") == "unverified":
                    state += " • certificado não verificado"
                labels.append(f"{service['scheme'].upper()} • {service['endpoint_ip']} • porta {service['port']} • {state}")
            choice, accepted = QInputDialog.getItem(self, "Abrir interface Web", "Selecione o serviço confirmado:", labels, 0, False)
            if not accepted or choice not in labels:
                return
            selected = services[labels.index(choice)]
        if not still_current():
            return
        url = build_web_service_url(selected["endpoint_ip"], selected["scheme"], selected["port"])
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Interface Web", "Não foi possível abrir a interface Web no navegador padrão.")

    def open_selected_device_web(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Interface Web", "Selecione um equipamento na tabela.")
            return
        site_id = self.current_site_id
        self._open_web_services(self._device_web_services(device_id),
                                lambda: self.current_site_id == site_id and self.selected_device_id() == device_id)

    def show_device_context_menu(self, pos):
        index = self.dev_table.indexAt(pos)
        if not index.isValid():
            return
        self.dev_table.selectRow(index.row())
        device_id = self.selected_device_id()
        if not device_id:
            return
        menu = QMenu(self)
        edit = QAction("Editar", self)
        edit.triggered.connect(self.edit_selected_device)
        menu.addAction(edit)
        diagnose_action = QAction("Diagnosticar", self)
        diagnose_action.triggered.connect(self.diagnose_selected)
        menu.addAction(diagnose_action)
        channels = QAction("Canais / testar stream", self)
        channels.triggered.connect(self.read_device_channels_or_stream)
        menu.addAction(channels)
        open_web = QAction("Abrir interface Web", self)
        web_services = self._device_web_services(device_id)
        open_web.setEnabled(bool(web_services))
        if web_services and web_services[0]["last_outcome"] != "confirmed":
            open_web.setToolTip("Confirmação histórica: a última tentativa falhou.")
            menu.setToolTipsVisible(True)
        open_web.triggered.connect(self.open_selected_device_web)
        menu.addAction(open_web)
        view_channels = QAction("Ver canais salvos", self)
        view_channels.triggered.connect(self.show_saved_channels)
        menu.addAction(view_channels)
        intelbras_api = QAction("Testar API Intelbras (somente leitura)", self)
        intelbras_api.triggered.connect(self.diagnose_selected_intelbras_http)
        menu.addAction(intelbras_api)
        menu.addSeparator()
        forget = QAction("Esquecer credencial", self)
        forget.triggered.connect(self.forget_selected_device_credential)
        menu.addAction(forget)
        export_profile = QAction("Exportar perfil AKDB", self)
        export_profile.triggered.connect(self.export_selected_compatibility_report)
        menu.addAction(export_profile)
        menu.addSeparator()
        archive = QAction("Arquivar equipamento…", self)
        archive.triggered.connect(self.archive_selected_device)
        menu.addAction(archive)
        ignore = QAction("Ignorar descoberta", self)
        ignore.triggered.connect(self.ignore_selected_device)
        menu.addAction(ignore)
        restore = QAction("Ver arquivados / restaurar", self)
        restore.triggered.connect(self.show_archived_devices)
        menu.addAction(restore)
        menu.addSeparator()
        delete = QAction("Excluir permanentemente…", self)
        delete.triggered.connect(self.delete_selected_device)
        menu.addAction(delete)
        menu.popup(self.dev_table.viewport().mapToGlobal(pos))
        self._device_context_menu = menu

    def export_selected_compatibility_report(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Perfil AKDB", "Selecione um equipamento na tabela.")
            return
        device = self.db.get_device(device_id)
        channels = self.db.list_recorder_channels(device_id)
        suggested = default_filename(device)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar perfil técnico para AKDB",
            str(data_dir() / suggested),
            "JSON (*.json)",
        )
        if not path:
            return
        report = build_compatibility_report(
            device, channels, sentinel_version=__version__, akdb_profiles=public_summary()
        )
        try:
            out = write_report(path, report)
        except Exception as exc:
            QMessageBox.warning(self, "Perfil AKDB", f"Não foi possível salvar o relatório: {exc}")
            return
        shared_note = ""
        try:
            candidate = record_compatibility_candidate(report, source_version=__version__)
            shared_note = (
                f"\n\nEvidência candidata #{candidate['id']} também registrada na AKDB compartilhada. "
                "Ela não altera automaticamente o conhecimento homologado."
            )
        except Exception as exc:
            shared_note = f"\n\nAKDB compartilhada: não foi possível registrar a evidência candidata ({exc})."
        QMessageBox.information(
            self,
            "Perfil AKDB exportado",
            f"Relatório salvo em:\n{out}\n\nCredenciais, IP, MAC, serial e URLs autenticadas foram omitidos/redigidos." + shared_note,
        )

    @requires_permission('device_edit')
    def edit_selected_device(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Identificação", "Selecione um equipamento.")
            return
        device = self.db.get_device(device_id)
        if is_cloud_device(device):
            self.configure_intelbras_cloud_bridge(device)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Editar identificação")
        form = QFormLayout(dialog)
        name = QLineEdit(device["name"])
        manufacturer = QLineEdit(device["manufacturer"])
        model = QLineEdit(clean_model(device["manufacturer"], device["model"]).replace("—", ""))
        try:
            saved_access = json.loads(device["metadata_json"] or "{}").get("connection_mode", ACCESS_LOCAL)
        except (TypeError, ValueError, AttributeError):
            saved_access = ACCESS_LOCAL
        access = QComboBox()
        access.addItem("Rede local", ACCESS_LOCAL)
        access.addItem("Outro local • rede privada/VPN", ACCESS_PRIVATE)
        access.addItem("Outro local • conector por Site (piloto)", ACCESS_CONNECTOR)
        access.setCurrentIndex(max(0, access.findData(saved_access)))
        protocol = QComboBox()
        protocol.addItem("Automático (identidade conhecida)", "")
        protocol.addItem("Intelbras / Dahua (protocolo compatível)", "intelbras")
        protocol.addItem("Hikvision / JFL (protocolo compatível)", "hikvision")
        try:
            saved_protocol = json.loads(device["metadata_json"] or "{}").get("recorder_protocol", "")
        except (TypeError, ValueError, AttributeError):
            saved_protocol = ""
        protocol.setCurrentIndex(max(0, protocol.findData(saved_protocol)))
        kind = QComboBox()
        choices = [("Não identificado", "unknown"), ("Câmera IP", "camera"), ("DVR", "dvr"), ("NVR", "nvr"), ("DVR / Multi HD", "xvr")]
        for label, value in choices:
            kind.addItem(label, value)
        operational = resolve_operational_identity(device)
        selected_kind = str(device["manual_kind"] or "") if "manual_kind" in device.keys() else ""
        idx = max(0, kind.findData(selected_kind or operational.kind or device["kind"]))
        kind.setCurrentIndex(idx)
        detected_kind = device["detected_kind"] if "detected_kind" in device.keys() else device["kind"]
        detected_maker = device["detected_manufacturer"] if "detected_manufacturer" in device.keys() else device["manufacturer"]
        detected_model = device["detected_model"] if "detected_model" in device.keys() else device["model"]
        detected_provider = device["detected_provider"] if "detected_provider" in device.keys() else device["provider"]
        detected = QLabel(
            f"Detectado pelo Sentinel: {friendly_kind(detected_kind)} • "
            f"{detected_maker or 'fabricante não confirmado'} • {clean_model(detected_maker, detected_model)} • provider {detected_provider}"
        )
        detected.setWordWrap(True)
        detected.setStyleSheet("color:#90aab4;font-size:10px")
        operational_label = QLabel("Roteamento atual: " + routing_explanation(operational))
        operational_label.setWordWrap(True)
        operational_label.setStyleSheet("color:#9cc9b4;font-size:10px;font-weight:600")
        auto_identity = QCheckBox("Remover override manual e voltar a usar Detecção + AKDB")
        auto_identity.setChecked(False)
        form.addRow(detected)
        form.addRow(operational_label)
        form.addRow("", auto_identity)
        form.addRow("Nome amigável", name)
        form.addRow("Acesso", access)
        form.addRow("Protocolo do gravador", protocol)
        form.addRow("Tipo (manual)", kind)
        form.addRow("Fabricante (manual)", manufacturer)
        form.addRow("Modelo (manual)", model)
        from .registration_assist import add_reference_picker
        reference_picker=add_reference_picker(form,dialog,manufacturer,model,kind,protocol)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.db.update_device_identity(
                device_id,
                name.text().strip() or device["ip"],
                kind.currentData(),
                manufacturer.text().strip(),
                model.text().strip(),
            )
            self.db.merge_device_metadata(device_id, {"connection_mode": access.currentData(), "recorder_protocol": protocol.currentData()})
            if reference_picker.state['applied']:
                self.db.merge_device_metadata(device_id,{'manual_akdb_reference':reference_picker.state['applied']})
            if auto_identity.isChecked():
                self.db.clear_device_identity_override(device_id)
            self.refresh_all()

    def diagnose_selected(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        device = self.db.get_device(device_id)
        if is_cloud_device(device):
            self.configure_intelbras_cloud_bridge(device)
            return
        worker = Worker(diagnose, device["ip"], device["web_url"], device["rtsp_url"])
        worker.signals.result.connect(lambda result: self.show_diag(device, result))
        worker.signals.error.connect(lambda error: QMessageBox.warning(self, "Diagnóstico", error))
        self.start_qt_worker(worker)

    def show_diag(self, device, result):
        ports = ", ".join(map(str, result.open_ports)) or "nenhuma das portas comuns"
        latency = f"{result.latency_ms:.1f} ms" if result.latency_ms is not None else "—"
        text = (
            f"Equipamento: {device['name']} ({device['ip']})\n\nOnline: {'SIM' if result.online else 'NÃO'}\n"
            f"Ping: {'OK' if result.ping_ok else 'sem resposta'}\nLatência: {latency}\nPortas detectadas: {ports}\n"
            f"HTTP: {result.web_ok}\nRTSP: {result.rtsp_ok}\n\n" + "\n".join(result.details)
        )
        try:
            connection_mode = json.loads(device["metadata_json"] or "{}").get("connection_mode")
        except (TypeError, ValueError, AttributeError):
            connection_mode = ACCESS_LOCAL
        if connection_mode == ACCESS_PRIVATE:
            text += (
                "\n\nAcesso remoto por rede privada/VPN."
                + (" Sem resposta de rede; confirme a VPN e o endereço antes de ler canais."
                   if not result.online else " Rede alcançável; prossiga para leitura de canais.")
            )
        elif connection_mode == ACCESS_CONNECTOR:
            text += ("\n\nConector por Site: ping responde pelo próprio computador; verifique HTTP e RTSP "
                     "para saber se o DVR está alcançável pelos dois túneis SSH.")
        QMessageBox.information(self, "Diagnóstico somente leitura", text)

    def diagnose_selected_intelbras_http(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Intelbras HTTP API", "Selecione um equipamento Intelbras.")
            return
        device = self.db.get_device(device_id)
        if not device:
            return
        if is_cloud_device(device):
            QMessageBox.information(self, "Intelbras HTTP API",
                                    "A ponte piloto encaminha vídeo pelo NetSDK; a API HTTP não está disponível nessa rota.")
            return
        identity = " ".join(str(device[key] or "") for key in ("manufacturer", "model", "name", "provider")).casefold()
        if "intelbras" not in identity and "mibo" not in identity and "mhdx" not in identity:
            QMessageBox.information(
                self, "Intelbras HTTP API",
                "O equipamento selecionado não está identificado como Intelbras/Mibo. "
                "O probe específico não será executado para evitar consultas incompatíveis.",
            )
            return
        credentials = self._credentials_for_device(device_id)
        if not credentials:
            QMessageBox.information(
                self, "Intelbras HTTP API",
                "Não há credencial disponível nesta sessão. Use Canais / Stream para informar a credencial ou salve-a no cofre e tente novamente.",
            )
            return
        username, password = credentials
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        open_ports = metadata.get("open_ports") or [] if isinstance(metadata, dict) else []
        worker = Worker(
            probe_intelbras_http_api,
            str(device["ip"] or ""), username, password,
            web_url=str(device["web_url"] or ""), open_ports=open_ports,
        )
        worker.signals.result.connect(
            lambda report, did=device_id: self._show_intelbras_http_report(did, report)
        )
        worker.signals.error.connect(
            lambda error: QMessageBox.warning(self, "Intelbras HTTP API", "Falha no probe somente leitura: " + str(error))
        )
        self.start_qt_worker(worker)

    def _show_intelbras_http_report(self, device_id: int, report: IntelbrasHttpApiReport):
        if report is None:
            return
        self.db.merge_device_metadata(int(device_id), {"intelbras_http_api": report.as_metadata()})
        self.refresh_device_inspector()
        title = "Intelbras HTTP API — somente leitura"
        detail = report.safe_summary()
        if report.post_audio_candidate:
            detail += (
                "\n\nO equipamento declarou pelo menos uma saída de áudio. "
                "O endpoint oficial postAudio foi marcado apenas como candidato; nenhum áudio foi enviado neste teste."
            )
        elif report.supported:
            detail += "\n\nNenhuma transmissão ou alteração foi realizada."
        QMessageBox.information(self, title, detail)

    def diagnose_selected_hikvision(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Diagnóstico Hikvision", "Selecione um equipamento Hikvision.")
            return
        device = self.db.get_device(device_id)
        operational = resolve_operational_identity(device)
        provider = recorder_provider_hint(device, operational)
        if provider not in {"hikvision", "jfl"}:
            QMessageBox.information(
                self, "Diagnóstico Hikvision",
                "O equipamento selecionado não está roteado como Hikvision/JFL. "
                "O diagnóstico específico não será executado para evitar probes incompatíveis.",
            )
            return
        credentials = self._credentials_for_device(device_id)
        if not credentials:
            QMessageBox.information(
                self, "Diagnóstico Hikvision",
                "Não há credencial disponível nesta sessão. Use Canais primeiro ou salve a credencial no cofre seguro e tente novamente.",
            )
            return
        username, password = credentials
        worker = Worker(hikvision_compatibility_report, device["ip"], username, password)
        worker.signals.result.connect(lambda report: self._show_hikvision_compatibility_report(device, report))
        worker.signals.error.connect(lambda error: QMessageBox.warning(self, "Diagnóstico Hikvision", error))
        self.start_qt_worker(worker)

    def _show_hikvision_compatibility_report(self, device, report: str):
        try:
            log_dir = data_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"hikvision-compatibility-{int(device['id'])}.txt"
            path.write_text(str(report) + "\n", encoding="utf-8")
            suffix = f"\n\nRelatório salvo em: {path}"
        except Exception:
            suffix = ""
        QMessageBox.information(self, "Diagnóstico Hikvision — somente leitura", str(report) + suffix)

    # ---------- discovery ----------
    def go_discovery(self, start=False):
        self.show_page(self.PAGE_CONFIG)
        self.config_tabs.setCurrentIndex(0)
        if start:
            self.start_discovery()

    def discovery_clock_tick(self):
        self.discovery_seconds += 1
        self.devices_found_status.setText(f"Analisando… {self.discovery_seconds}s")

    def _discovery_web_candidates(self):
        # Snapshot hints on the UI thread; the discovery worker never reads SQLite.
        candidates = {}
        for device in self.db.list_devices(self.current_site_id, include_archived=True):
            for endpoint in self.db.list_device_endpoints(device["id"]):
                try:
                    targets = candidates.setdefault(endpoint["ip"], [])
                    for hint in (endpoint["web_url"], device["web_url"]):
                        for target in web_service_candidates(endpoint["ip"], hint):
                            if target not in targets:
                                targets.append(target)
                except ValueError:
                    continue
        return candidates

    def start_discovery(self):
        if not self.current_site_id or not self.devices_find_btn.isEnabled():
            return
        self.devices_find_btn.setEnabled(False)
        self.discovery_web_results = {}
        self._transient_web_checks = {}
        self._sync_selected_device_actions()
        self.devices_find_btn.setText("Analisando rede…")
        self.devices_found_table.setRowCount(0)
        self.discovery_results = []
        self.discovery_site_id = self.current_site_id
        self.devices_add_found_btn.setEnabled(False)
        self.devices_report_found_btn.setEnabled(False)
        self.devices_web_found_btn.setEnabled(False)
        self.devices_discovery_log.clear()
        self.devices_discovery_log.appendPlainText("Iniciando descoberta multiestratégia…")
        self.devices_found_progress.setRange(0, 0)
        self.discovery_seconds = 0
        self.devices_found_status.setText("Analisando… 0s")
        self.discovery_clock.start(1000)

        worker = Worker(discover_network_devices, self.current_site_id, with_progress=True,
                        web_candidates=self._discovery_web_candidates())
        worker.signals.progress.connect(self.devices_discovery_log.appendPlainText)
        worker.signals.result.connect(self.discovery_done)
        worker.signals.error.connect(self.discovery_error)
        worker.signals.finished.connect(self.discovery_finished)
        self.start_qt_worker(worker)

    def discovery_finished(self):
        self.discovery_clock.stop()
        self.devices_found_progress.setRange(0, 1)
        self.devices_found_progress.setValue(1)
        self.devices_find_btn.setEnabled(True)
        self.devices_find_btn.setText("Buscar / atualizar")

    def discovery_error(self, error):
        self.devices_discovery_log.appendPlainText("ERRO: " + error)
        self.devices_found_status.setText("Busca interrompida • abra Detalhes da busca para ver o erro")

    def _discovery_selection_changed(self):
        row = self.devices_found_table.currentRow()
        selected = 0 <= row < len(self.discovery_results)
        known = self.db.find_known_for_discovery(self.current_site_id, self.discovery_results[row]) if selected else None
        conflict=bool(selected and self.discovery_results[row].metadata.get('identity_conflicts'))
        included = bool(known and not known["archived"] and not conflict)
        self.devices_add_found_btn.setText("Revisar conflito" if conflict else "Ver incluído" if included else "Restaurar selecionado" if known and known["archived"] else "Adicionar selecionado")
        self.devices_add_found_btn.setEnabled(selected)
        self.devices_found_channels_btn.setEnabled(included)
        self.devices_found_delete_btn.setEnabled(included)
        self.devices_report_found_btn.setEnabled(selected)
        self.devices_web_found_btn.setEnabled(bool(
            selected and self._found_web_services(self.discovery_results[row])
        ))

    def _found_web_services(self, device):
        if getattr(self, "discovery_web_site_id", None) != self.current_site_id:
            return []
        checks = getattr(self, "discovery_web_results", {}).get(device.ip, [])
        return ordered_web_services(web_services_from_checks(checks, endpoint_ip=device.ip))

    def act_on_found_device(self, action):
        row = self.devices_found_table.currentRow()
        if not 0 <= row < len(self.discovery_results):
            return
        if self.discovery_results[row].metadata.get('identity_conflicts'):return
        known = self.db.find_known_for_discovery(self.current_site_id, self.discovery_results[row])
        if not known or known["archived"]:
            return
        self.device_filter.clear()
        for index in range(self.dev_table.rowCount()):
            item = self.dev_table.item(index, 0)
            if item and item.data(Qt.UserRole) == int(known["id"]):
                self.dev_table.selectRow(index)
                action()
                self.refresh_discovery_registration()
                return

    def refresh_discovery_registration(self):
        included_count = 0
        for row, device in enumerate(self.discovery_results):
            known = self.db.find_known_for_discovery(self.current_site_id, device)
            conflict=bool(device.metadata.get('identity_conflicts'))
            included = bool(known and not known["archived"] and not conflict)
            included_count += int(included)
            state = "* Incluído" if included else "Arquivado • restaurar" if known and known["archived"] else "Novo • validar"
            if conflict:state='Conflito • revisar'
            if known and known["ignored_discovery"]:
                state += " • ignorado"
            item = self.devices_found_table.item(row, 4)
            if item:
                item.setText(state)
                item.setForeground(QColor("#94e2b8" if included else "#d7c99d"))
                item.setToolTip("Equipamento já incluído: use Canais ou Excluir." if included else state)
        self.devices_found_status.setText(f"{len(self.discovery_results)} localizado(s) • {included_count} incluído(s)")
        self._discovery_selection_changed()

    def open_discovered_device_web(self):
        row = self.devices_found_table.currentRow()
        if row < 0 or row >= len(self.discovery_results):
            return
        device = self.discovery_results[row]
        site_id = self.current_site_id
        self._open_web_services(self._found_web_services(device),
                                lambda: self.current_site_id == site_id
                                and self.devices_found_table.currentRow() == row
                                and row < len(self.discovery_results) and self.discovery_results[row] is device)

    def discovery_done(self, report):
        if (self.discovery_site_id != self.current_site_id
                or getattr(report, "site_id", self.discovery_site_id) not in (None, self.current_site_id)):
            self.devices_found_status.setText("Site alterado; faça uma nova busca neste Site.")
            self.discovery_results = []
            self.devices_found_table.setRowCount(0)
            return
        self.discovery_web_site_id = self.current_site_id
        self.discovery_web_results = getattr(report, "web_results", {})
        if report.interfaces:
            self.devices_discovery_log.appendPlainText("Interfaces: " + " | ".join(report.interfaces))
        self.devices_discovery_log.appendPlainText(
            f"Concluído: {report.addresses_scanned} endereço(s) avaliados; "
            f"{report.responsive_hosts} host(s) com serviços comuns; {len(report.devices)} possível(is) CFTV; "
            f"{len(report.other_hosts)} outro(s) host(s)."
        )
        for host in report.other_hosts[:20]:
            self.devices_discovery_log.appendPlainText(f"Rede • {host} • sem evidência CFTV")
        if len(report.other_hosts) > 20:
            self.devices_discovery_log.appendPlainText(f"Rede • mais {len(report.other_hosts) - 20} host(s) omitidos")

        discovered_ips = {device.ip for device in report.devices}
        for ip, checks in self.discovery_web_results.items():
            if ip in discovered_ips:
                continue
            endpoint_device = Device(site_id=self.current_site_id, ip=ip)
            known = self.db.find_known_for_discovery(self.current_site_id, endpoint_device)
            if known:
                self._remember_discovered_web_checks(known["id"], endpoint_device, checks)
        self._sync_selected_device_actions()

        # Retain registered devices alongside new discoveries for channel management.
        new_devices = []
        known_count = archived_count = ignored_count = endpoint_updates = 0
        for device in report.devices:
            device.site_id = self.current_site_id
            known = self.db.find_known_for_discovery(self.current_site_id, device)
            from .registration_assist import registration_conflicts
            conflicts=registration_conflicts(known,device)
            if conflicts:
                device.metadata['identity_conflicts']=conflicts
                new_devices.append(device)
                self.devices_discovery_log.appendPlainText(f'{device.ip} • identidade em conflito; cadastro anterior preservado.')
                continue
            if known:
                if int(known["archived"] or 0) and not int(known["ignored_discovery"] or 0):
                    # Restoration is a user choice; display this unit instead
                    # of silently suppressing it with active known devices.
                    new_devices.append(device)
                    archived_count += 1
                    self._remember_discovered_web_checks(known["id"], device,
                                                        self.discovery_web_results.get(device.ip, []))
                    continue
                before_ips = {str(ep["ip"]) for ep in self.db.list_device_endpoints(int(known["id"]))}
                canonical_id = self.db.upsert_device(device)
                self._remember_discovered_web_checks(canonical_id, device,
                                                    self.discovery_web_results.get(device.ip, []))
                after_ips = {str(ep["ip"]) for ep in self.db.list_device_endpoints(int(canonical_id))}
                if after_ips - before_ips:
                    endpoint_updates += 1
                    self.devices_discovery_log.appendPlainText(
                        f"Conhecido: {device.ip} correlacionado como novo endpoint de {known['name'] or known['model'] or 'equipamento'}."
                    )
                known_count += 1
                if int(known["archived"] or 0):
                    archived_count += 1
                if int(known["ignored_discovery"] or 0):
                    ignored_count += 1
                new_devices.append(device)
                continue
            new_devices.append(device)

        if known_count:
            self.devices_discovery_log.appendPlainText(
                f"{known_count} equipamento(s) já cadastrados reconhecidos e marcados como incluídos"
                + (f"; {endpoint_updates} novo(s) endpoint(s) associado(s)" if endpoint_updates else "")
                + "."
            )

        if not new_devices:
            self.discovery_results = []
            self.devices_found_table.setRowCount(0)
            self.devices_found_status.setText("Nenhum equipamento novo localizado • use Adicionar para cadastrar por IP")
            if report.devices:
                self.devices_found_status.setText(f"Nenhum novo equipamento • {known_count} conhecido(s)")
            else:
                self.devices_found_status.setText("Nenhum CFTV identificado")
                self.devices_discovery_log.appendPlainText(
                    "Nenhum equipamento foi identificado pelos métodos atuais. Isso pode ocorrer se ONVIF/RTSP estiver desativado, "
                    "o equipamento usar somente descoberta proprietária ou estiver em outra faixa/VLAN."
                )
            return

        self.devices_found_status.setText(f"{len(new_devices)} encontrado(s) • novos ou arquivados para restaurar")
        self.discovery_results = list(new_devices)
        self.devices_found_table.setRowCount(len(new_devices))
        for row, device in enumerate(new_devices):
            ports = device.metadata.get("open_ports", [])
            sources = device.metadata.get("discovery_sources", [])
            evidence = device.metadata.get("evidence", [])
            parts = []
            for value in (device.manufacturer, device.model):
                value = (value or "").strip()
                if value and value.lower() not in {x.lower() for x in parts}:
                    parts.append(value)
            ident = " ".join(parts) or device.name
            service_text = ", ".join(map(str, ports)) or ("ONVIF" if device.onvif_url else "—")
            confidence = int(device.metadata.get("akdb_confidence", device.metadata.get("identity_confidence", 0)) or 0)
            stable_id = str(device.metadata.get("akdb_stable_id") or "")
            subtype = str(device.metadata.get("device_subtype") or "")
            canonical = str(device.metadata.get("canonical_type") or "unknown")
            homologation = str(device.metadata.get("homologation_status") or "candidate")
            ev_parts = list(sources + evidence)
            ev_parts.extend(str(reason) for reason in device.metadata.get("akdb_reasons", []) if reason)
            if stable_id:
                ev_parts.insert(0, f"AKDB {confidence}% • {canonical}" + (f"/{subtype}" if subtype else "") + f" • {homologation}")
            else:
                ev_parts.insert(0, "NOVO • candidato à homologação AKDB")
            from .registration_assist import evidence_summary
            ev_parts.append(evidence_summary(device.metadata))
            ev = "; ".join(str(v) for v in ev_parts if v) or "—"
            if confidence:
                ident = f"{ident} • {confidence}%"
            known = self.db.find_known_for_discovery(self.current_site_id, device)
            found_values = (device.ip, friendly_kind(str(device.kind)), ident, service_text,
                            "Arquivado • restaurar" if known and known["archived"] else "Conflito • revisar" if device.metadata.get("identity_conflicts") else "Possível CFTV • validar", ev)
            for col, value in enumerate(found_values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(ev)
                self.devices_found_table.setItem(row, col, item)
        self.refresh_discovery_registration()
        self._sync_selected_device_actions()

    @requires_permission('device_add')
    def add_found_from_devices(self):
        row = self.devices_found_table.currentRow()
        if row < 0 or row >= len(self.discovery_results):
            return
        self.add_discovered_selected()

    def export_discovered_homologation_report(self):
        row = self.devices_found_table.currentRow()
        if row < 0 or row >= len(self.discovery_results):
            QMessageBox.information(self, "AKDB", "Selecione um equipamento descoberto.")
            return
        device = self.discovery_results[row]
        suggested = discovery_report_filename(device)
        path, _ = QFileDialog.getSaveFileName(
            self, "Relatório de homologação AKDB", str(data_dir() / suggested), "JSON (*.json)"
        )
        if not path:
            return
        report = build_discovery_homologation_report(device, sentinel_version=__version__)
        try:
            from artin_akdb import write_field_report
            out = write_field_report(path, report)
            candidate = record_field_homologation_report(report, source_version=__version__)
        except Exception as exc:
            QMessageBox.warning(self, "AKDB", f"Não foi possível gerar o relatório: {exc}")
            return
        QMessageBox.information(
            self, "Relatório AKDB",
            f"Relatório sanitizado salvo em:\n{out}\n\n"
            f"Candidato local #{candidate['report_id']} • geração AKDB {candidate['local_generation']}.\n"
            "O relatório não promove conhecimento automaticamente; ele fica pronto para revisão/homologação."
        )

    @requires_permission('device_add')
    def add_discovered_selected(self):
        if getattr(self, "discovery_web_site_id", self.current_site_id) != self.current_site_id:
            return
        row = self.devices_found_table.currentRow()
        if row < 0 or row >= len(self.discovery_results):
            return
        device = self.discovery_results[row]
        from .registration_assist import evidence_summary,registration_conflicts
        known=self.db.find_known_for_discovery(self.current_site_id,device)
        device.metadata['identity_conflicts']=registration_conflicts(known,device)
        if device.metadata.get('identity_conflicts'):
            QMessageBox.information(self,'Identidade requer revisão',evidence_summary(device.metadata)+'\n\nCadastre por Adicionar e escolha a identificação/protocolo, ou revise a descoberta. Nenhum cadastro foi alterado.')
            return
        device.site_id = self.current_site_id
        known = self.db.find_known_for_discovery(self.current_site_id, device)
        if known and not known["archived"]:
            self.act_on_found_device(self.refresh_device_inspector)
            return
        if known and known["ignored_discovery"]:
            QMessageBox.information(self, "Descoberta", "Este equipamento está marcado como ignorado. Remova a marca em Equipamentos antes de adicioná-lo novamente.")
            return
        if known and known["archived"]:
            if not authorize(self,'device_edit'):return
            answer = QMessageBox.question(self, "Equipamento arquivado", "Este equipamento já existia e está arquivado. Restaurar o cadastro anterior?")
            if answer != QMessageBox.Yes:
                return
            self.db.archive_device(known["id"], False)
            self.db.set_ignore_discovery(known["id"], False)
        device_id = self.db.upsert_device(device)
        self._remember_discovered_web_checks(device_id, device,
                                            getattr(self, "discovery_web_results", {}).get(device.ip, []),
                                            confirmed_only=True)
        self.db.add_event(self.current_site_id, device_id, "info", "device_added", f"{device.name} ({device.ip}) adicionado ao Site.")
        self.devices_discovery_log.appendPlainText(f"Adicionado ao Site: {device.ip} — {device.name}")
        self.refresh_all()
        self.refresh_discovery_registration()
        QMessageBox.information(
            self,
            "Equipamento",
            "Equipamento adicionado ao Site. Ele já aparece na árvore do monitoramento e pode ser diagnosticado em Configuração.",
        )

    # ---------- recorder onboarding ----------
    def _pause_monitor_for_recorder(self):
        if self.monitor.isActive():
            self.monitor.stop()
            self._monitor_paused_for_recorder = True

    def _resume_monitor_after_recorder(self):
        if self._monitor_paused_for_recorder:
            self.monitor.start(30000)
            self._monitor_paused_for_recorder = False
        self.channel_health_inflight = set()

    @requires_permission('device_edit')
    def forget_selected_device_credential(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Credencial", "Selecione um equipamento.")
            return
        device = self.db.get_device(device_id)
        self.session_credentials.pop(device_id, None)
        result = self.credential_store.delete_password(device_id)
        self.db.update_device_credential_meta(device_id, device["credential_username"] or "", False)
        self.refresh_all()
        box = QMessageBox(self)
        box.setWindowTitle("Credencial")
        box.setIcon(QMessageBox.Information)
        box.setText("A credencial salva foi removida. A senha não está armazenada no SQLite.")
        if not result.ok and self.credential_store.available:
            box.setInformativeText(result.message)
        box.setStandardButtons(QMessageBox.Ok)
        box.setModal(True)
        box.open()
        box.setAttribute(Qt.WA_DeleteOnClose, True)

    def _stop_device_live_sessions(self, device_id: int):
        for tile in list(self.video_tiles):
            if tile.source and int(tile.source.get("device_id", -1)) == int(device_id):
                self.close_tile_source(tile)

    def show_archived_devices(self):
        rows = self.db.list_archived_devices(self.current_site_id)
        if not rows:
            QMessageBox.information(self, "Arquivados", "Não há equipamentos arquivados neste Site.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Equipamentos arquivados")
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["ID", "Nome", "IP", "Fabricante / modelo"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for r, dev in enumerate(rows):
            vals = (dev["id"], dev["name"], dev["ip"], f"{dev['manufacturer']} {clean_model(dev['manufacturer'], dev['model'])}".strip())
            for c, value in enumerate(vals):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        restore = QPushButton("Restaurar selecionado")
        buttons.addButton(restore, QDialogButtonBox.ActionRole)
        restore.clicked.connect(lambda: self._restore_archived_from_table(dialog, table))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(720, 420)
        self._transient_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0, d=dialog: self._release_transient_dialog(d))
        dialog.open()

    @requires_permission('device_edit')
    def _restore_archived_from_table(self, dialog, table):
        row = table.currentRow()
        if row < 0 or not table.item(row, 0):
            return
        device_id = int(table.item(row, 0).text())
        self.db.archive_device(device_id, False)
        self.db.set_ignore_discovery(device_id, False)
        self.refresh_all()
        dialog.accept()

    @requires_permission('device_edit')
    def archive_selected_device(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        device = self.db.get_device(device_id)
        answer = QMessageBox.question(
            self, "Arquivar equipamento",
            f"Remover '{device['name']}' da operação ativa e preservar histórico/evidências?",
        )
        if answer != QMessageBox.Yes:
            return
        self._stop_device_live_sessions(device_id)
        self.db.archive_device(device_id, True)
        self.refresh_all()

    @requires_permission('device_edit')
    def ignore_selected_device(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        self.db.set_ignore_discovery(device_id, True)
        QMessageBox.information(self, "Descoberta", "O equipamento foi marcado para ser ignorado nas próximas inclusões automáticas.")
        self.refresh_all()

    @requires_permission('device_edit')
    def delete_selected_device(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        device = self.db.get_device(device_id)
        answer = QMessageBox.warning(
            self, "Excluir permanentemente",
            f"Excluir permanentemente '{device['name']}'?\n\nSerão removidos canais, vínculos de layout, histórico deste equipamento e a credencial salva. Esta ação não afeta outros equipamentos.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._stop_device_live_sessions(device_id)
        try:
            self.credential_store.delete_password(device_id)
        except Exception:
            pass
        self.db.delete_device_permanently(device_id)
        self.session_credentials.pop(device_id, None)
        self.refresh_all()

    @requires_permission('device_edit')
    def read_device_channels_or_stream(self):
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Canais / stream", "Selecione um equipamento na tabela.")
            return
        device = self.db.get_device(device_id)
        if not device:
            return
        if is_cloud_device(device):
            self.configure_intelbras_cloud_bridge(device)
            return
        operational = resolve_operational_identity(device)
        if operational.kind == "camera":
            self.read_direct_camera_stream(device_id, device)
        elif operational.kind in {"dvr", "nvr", "xvr"}:
            self.read_recorder_channels()
        else:
            QMessageBox.information(
                self, "Canais / stream",
                "O tipo operacional ainda não está definido. Corrija o Tipo em Equipamentos ou homologue o modelo na AKDB antes de testar canais."
            )

    @requires_permission('device_edit')
    def read_direct_camera_stream(self, device_id: int, device):
        if self.channel_scan_context is not None or self.recorder_credentials_dialog is not None:
            QMessageBox.information(self, "Câmera IP", "Já existe um teste de stream/leitura em andamento.")
            return
        self._pause_monitor_for_recorder()
        dialog = QDialog(self)
        dialog.setWindowTitle("Acesso somente leitura à câmera IP")
        dialog.setModal(True)
        form = QFormLayout(dialog)
        info = QLabel(
            f"{device['name']} • {device['ip']}\n"
            "O Sentinel tentará ONVIF Device/Media/GetStreamUri e, se necessário, padrões RTSP da AKDB/provider. "
            "Nenhuma configuração da câmera será alterada."
        )
        info.setWordWrap(True)
        friendly_name = QLineEdit(device["name"] or device["ip"])
        user = QLineEdit()
        session_user, session_secret = self.session_credentials.get(device_id, ("", ""))
        saved_secret = self.credential_store.get_password(device_id) if device["credential_saved"] else None
        user.setText(device["credential_username"] or session_user or "admin")
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        if saved_secret is not None:
            password.setText(saved_secret)
        elif session_secret:
            password.setText(session_secret)
        save_secret = QCheckBox("Salvar credencial com segurança")
        save_secret.setChecked(bool(device["credential_saved"] and saved_secret is not None))
        save_secret.setEnabled(self.credential_store.available)
        route = QLabel("Rota: Direta • ONVIF/RTSP")
        route.setStyleSheet("color:#90aab4;font-size:10px")
        form.addRow(info)
        form.addRow("Nome amigável", friendly_name)
        form.addRow("Usuário", user)
        form.addRow("Senha", password)
        form.addRow("", save_secret)
        form.addRow(route)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Testar stream")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        self.recorder_credentials_dialog = dialog
        self.recorder_credentials_inputs = (device_id, device, friendly_name, user, password, save_secret, "camera")
        dialog.accepted.connect(self._camera_credentials_accepted)
        dialog.rejected.connect(self._recorder_credentials_rejected)
        dialog.finished.connect(self._recorder_credentials_finished)
        dialog.open()
        password.setFocus()

    @requires_permission('device_edit')
    def _camera_credentials_accepted(self):
        inputs = self.recorder_credentials_inputs
        if not inputs:
            return
        device_id, device, friendly_name, user, password, save_secret, _kind = inputs
        username, secret = user.text().strip() or "admin", password.text()
        new_name = friendly_name.text().strip() or device["ip"]
        if new_name != device["name"]:
            self.db.update_device_identity(device_id, new_name, device["kind"], device["manufacturer"], device["model"])
            device = self.db.get_device(device_id)
        self.session_credentials[device_id] = (username, secret)
        self.credential_save_notice = ""
        if save_secret.isChecked():
            result = self.credential_store.set_password(device_id, secret)
            self.db.update_device_credential_meta(device_id, username, result.ok)
            self.credential_save_notice = result.message
        else:
            if device["credential_saved"]:
                self.credential_store.delete_password(device_id)
            self.db.update_device_credential_meta(device_id, username, False)
        self.refresh_all()
        self._start_direct_camera_scan(device_id, device, username, secret)

    def _start_direct_camera_scan(self, device_id, device, username, secret):
        cancel_event = Event()
        progress_queue = Queue()
        wait = QDialog(self)
        wait.setWindowTitle("Artin Sentinel — Teste da câmera IP")
        wait.setModal(True)
        layout = QVBoxLayout(wait)
        label = QLabel("Consultando ONVIF Media Profiles e validando RTSP direto…")
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar(); progress.setRange(0, 0); layout.addWidget(progress)
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.cancel_recorder_channel_scan); layout.addWidget(cancel, 0, Qt.AlignRight)
        wait.setMinimumWidth(500)
        self.channel_scan_context = {"device_id": device_id, "device": device, "wait": wait, "label": label, "cancel": cancel, "direct_camera": True}
        self.channel_scan_cancel_event = cancel_event
        self.channel_scan_progress_queue = progress_queue
        self.channels_button.setEnabled(False)
        def report_progress(message):
            progress_queue.put(sanitize_talkback_diagnostic(message, username, secret))
        self.channel_scan_future = self.recorder_executor.submit(
            scan_direct_camera_streams,
            device["ip"], username, secret,
            provider=device["provider"],
            manufacturer_hint=device["manufacturer"], model_hint=device["model"], name_hint=device["name"],
            onvif_url=device["onvif_url"], rtsp_url=device["rtsp_url"],
            progress=report_progress, cancel_event=cancel_event,
            previous_channels=[dict(row) for row in self.db.list_recorder_channels(device_id)],
        )
        wait.open()
        self.channel_scan_poll_timer.start()

    @requires_permission('device_edit')
    def read_recorder_channels(self):
        if self.channel_scan_context is not None or self.recorder_credentials_dialog is not None:
            QMessageBox.information(self, "Gravador", "Já existe uma leitura de canais em andamento.")
            return
        device_id = self.selected_device_id()
        if not device_id:
            QMessageBox.information(self, "Gravador", "Selecione um equipamento na tabela.")
            return
        device = self.db.get_device(device_id)
        if is_cloud_device(device):
            self.configure_intelbras_cloud_bridge(device)
            return
        operational = resolve_operational_identity(device)
        if operational.kind not in ("dvr", "nvr", "xvr"):
            QMessageBox.information(
                self, "Leitura de canais",
                "O equipamento não está roteado como gravador. "
                f"Estado operacional: {routing_explanation(operational)}.\n\n"
                "Corrija o Tipo em Equipamentos ou homologue o perfil na AKDB; o Sentinel não executará enumeração ampla como câmera por engano.",
            )
            return
        recorder_provider = recorder_provider_hint(device, operational)
        if recorder_provider == "generic":
            QMessageBox.information(
                self,
                "Leitura de canais",
                "O equipamento está marcado como gravador, mas a família de protocolo ainda não foi identificada. "
                "Informe fabricante/modelo em Equipamentos ou homologue o modelo na AKDB antes da enumeração. "
                "O Sentinel não assume Intelbras/Dahua como fallback para um gravador desconhecido.",
            )
            return

        # Keep one Qt event loop only. The 0.1.5 field fix intentionally avoids
        # a nested modal event loop in recorder onboarding because it caused a native
        # Shiboken/PySide6 crash on Fedora 44.
        self._pause_monitor_for_recorder()
        dialog = QDialog(self)
        dialog.setWindowTitle("Acesso somente leitura ao gravador")
        dialog.setModal(True)
        form = QFormLayout(dialog)
        model = clean_model(device["manufacturer"], device["model"])
        model_line = f"Modelo: {model}\n" if model != "—" else f"Provider: {device['provider']}\n"
        info = QLabel(
            f"{device['ip']}\n" + model_line +
            "A senha pode ser mantida apenas nesta sessão ou salva no cofre seguro do sistema. "
            "Ela nunca é gravada em texto puro no SQLite."
        )
        info.setWordWrap(True)
        friendly_name = QLineEdit(device["name"] or device["ip"])
        user = QLineEdit()
        session_user, session_secret = self.session_credentials.get(device_id, ("", ""))
        saved_secret = None
        if device["credential_saved"]:
            saved_secret = self.credential_store.get_password(device_id)
        user.setText(device["credential_username"] or session_user or "admin")
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        if saved_secret is not None:
            password.setText(saved_secret)
        elif session_secret:
            password.setText(session_secret)
        save_secret = QCheckBox("Salvar credencial com segurança")
        save_secret.setChecked(bool(device["credential_saved"] and saved_secret is not None))
        save_secret.setEnabled(self.credential_store.available)
        try:
            recorder_metadata = json.loads(device["metadata_json"] or "{}")
        except (TypeError, ValueError):
            recorder_metadata = {}
        if not isinstance(recorder_metadata, dict):
            recorder_metadata = {}
        profile_key = self._selected_device_profile_key(device)
        scan_capacity = QSpinBox()
        scan_capacity.setRange(1, 64)
        akdb_capacity = recorder_scan_capacity_for_device(
            provider=recorder_provider, profile_key=profile_key,
            model=str(device["model"] or ""), name=str(device["name"] or ""),
            saved_source="akdb",
        )
        scan_capacity.setProperty("akdb_default", akdb_capacity)
        scan_capacity.setValue(recorder_scan_capacity_for_device(
            provider=recorder_provider, profile_key=profile_key,
            model=str(device["model"] or ""), name=str(device["name"] or ""),
            saved_limit=recorder_metadata.get("channel_scan_limit"),
            saved_source=recorder_metadata.get("channel_scan_source", ""),
        ))
        scan_capacity.setToolTip(
            "O número limita a busca sem inventário. IDs anunciados pela ISAPI são preservados, "
            "inclusive entradas IP acima desse número. Alterações ficam salvas apenas neste gravador; "
            "somente canais com vídeo confirmado ficam disponíveis no Ao vivo."
        )
        rtsp_port = QSpinBox()
        rtsp_port.setRange(1, 65535)
        _web_port, configured_rtsp = forwarded_ports(device["ip"], device["web_url"], device["rtsp_url"])
        rtsp_port.setValue(int(recorder_metadata.get("recorder_rtsp_port") or configured_rtsp))
        rtsp_port.setToolTip("Porta RTSP deste gravador; usada na leitura Hikvision e nos canais salvos")
        keyring_status = QLabel(self.credential_store.status_message)
        keyring_status.setWordWrap(True)
        keyring_status.setStyleSheet("color:#90aab4;font-size:10px")
        form.addRow(info)
        form.addRow("Nome amigável", friendly_name)
        form.addRow("Usuário", user)
        form.addRow("Senha", password)
        form.addRow("Canais a verificar", scan_capacity)
        if recorder_provider in ("hikvision", "jfl"):
            form.addRow("Porta RTSP", rtsp_port)
        form.addRow("Padrão AKDB", QLabel(f"{akdb_capacity} posições • {profile_key or 'modelo não identificado'}"))
        form.addRow("", save_secret)
        form.addRow("Cofre", keyring_status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Ler canais")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        self.recorder_credentials_dialog = dialog
        self.recorder_credentials_inputs = (device_id, device, friendly_name, user, password, save_secret, scan_capacity, rtsp_port)
        dialog.accepted.connect(self._recorder_credentials_accepted)
        dialog.rejected.connect(self._recorder_credentials_rejected)
        dialog.finished.connect(self._recorder_credentials_finished)
        dialog.open()
        password.setFocus()

    @requires_permission('device_edit')
    def _recorder_credentials_accepted(self):
        inputs = self.recorder_credentials_inputs
        if inputs is None:
            return
        device_id, device, friendly_name, user, password, save_secret, scan_capacity, rtsp_port = inputs
        username, secret = user.text().strip(), password.text()
        if not username:
            username = "admin"
        new_name = friendly_name.text().strip() or device["ip"]
        if new_name != device["name"]:
            self.db.update_device_identity(
                device_id, new_name, device["kind"], device["manufacturer"], device["model"]
            )
            device = self.db.get_device(device_id)

        akdb_capacity = int(scan_capacity.property("akdb_default") or 0)
        self.db.merge_device_metadata(device_id, {
            "channel_scan_limit": scan_capacity.value(),
            "channel_scan_source": "akdb" if scan_capacity.value() == akdb_capacity else "manual",
            "recorder_rtsp_port": rtsp_port.value(),
        })
        device = self.db.get_device(device_id)
        self.session_credentials[device_id] = (username, secret)
        self.credential_save_notice = ""
        if save_secret.isChecked():
            result = self.credential_store.set_password(device_id, secret)
            self.db.update_device_credential_meta(device_id, username, result.ok)
            self.credential_save_notice = result.message
        else:
            if device["credential_saved"]:
                self.credential_store.delete_password(device_id)
            self.db.update_device_credential_meta(device_id, username, False)
        self.refresh_all()
        self._start_recorder_channel_scan(device_id, device, username, secret)

    def _recorder_credentials_rejected(self):
        self._resume_monitor_after_recorder()

    def _recorder_credentials_finished(self, _result):
        self.recorder_credentials_dialog = None
        self.recorder_credentials_inputs = None
        if self.channel_scan_context is None:
            self._resume_monitor_after_recorder()

    def _start_recorder_channel_scan(self, device_id, device, username, secret):
        operational = resolve_operational_identity(device)
        provider = recorder_provider_hint(device, operational)
        if provider == "generic":
            self._resume_monitor_after_recorder()
            QMessageBox.information(
                self, "Protocolo do gravador",
                "Não foi possível identificar o protocolo de leitura. "
                "Em Editar identificação, escolha a família de protocolo do gravador "
                "e tente novamente. Nenhum canal existente foi alterado."
            )
            return
        cancel_event = Event()
        progress_queue = Queue()

        wait = QDialog(self)
        wait.setWindowTitle("Artin Sentinel — Leitura de canais")
        wait.setModal(True)
        layout = QVBoxLayout(wait)
        label = QLabel("Validando RTSP do gravador e compatibilidade Digest/URL…")
        if self.credential_save_notice:
            label.setText(label.text() + "\n" + self.credential_save_notice)
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.cancel_recorder_channel_scan)
        layout.addWidget(cancel, 0, Qt.AlignRight)
        wait.setMinimumWidth(470)

        self.channel_scan_context = {
            "device_id": device_id,
            "device": device,
            "wait": wait,
            "label": label,
            "cancel": cancel,
            "remote_recorder": json.loads(device["metadata_json"] or "{}").get("connection_mode") in (ACCESS_PRIVATE, ACCESS_CONNECTOR),
        }
        self.channel_scan_cancel_event = cancel_event
        self.channel_scan_progress_queue = progress_queue
        self.channels_button.setEnabled(False)

        def report_progress(message):
            # Called only from the Python worker thread. Never touch Qt here.
            progress_queue.put(str(message))

        scan_fn = scan_hikvision_channels if provider in ("hikvision", "jfl") else scan_intelbras_channels
        profile_label = "Hikvision/JFL" if scan_fn is scan_hikvision_channels else "Intelbras/Dahua"
        profile_key = self._selected_device_profile_key(device)
        try:
            scan_metadata = json.loads(device["metadata_json"] or "{}")
        except (TypeError, ValueError):
            scan_metadata = {}
        if not isinstance(scan_metadata, dict):
            scan_metadata = {}
        max_channels = recorder_scan_capacity_for_device(
            provider=provider, profile_key=profile_key, model=str(device["model"] or ""),
            name=str(device["name"] or ""), saved_limit=scan_metadata.get("channel_scan_limit"),
            saved_source=scan_metadata.get("channel_scan_source", ""),
        )
        limit_text = f" • {max_channels} posições selecionadas"
        route_info = resolve_operational_identity(device)
        label.setText(
            f"Perfil {profile_label} ativo • {routing_explanation(route_info)}\n"
            f"Validando RTSP e enumerando canais lógicos{limit_text}…"
        )
        kwargs = dict(progress=report_progress, cancel_event=cancel_event)
        # The selected per-device capacity wins over a stale vendor-only AKDB
        # match. For MHDX 1004 the default remains 4 analogue + 1 IP channel.
        kwargs["max_channels"] = max_channels
        if scan_fn is scan_intelbras_channels:
            http_port, rtsp_port = forwarded_ports(device["ip"], device["web_url"], device["rtsp_url"])
            model_text = f"{device['model'] or ''} {device['name'] or ''}".casefold()
            layout = ("mhdx1004" if any(token in model_text for token in ("mhdx 1004", "mhdx1004"))
                      else "nvr" if profile_key in {"intelbras-nvd-1416", "intelbras-nvd-1516"}
                      or str(operational.kind) == "nvr" else "unknown")
            kwargs.update(http_port=http_port, rtsp_port=rtsp_port, channel_layout=layout)
        else:
            _web_port, configured_rtsp = forwarded_ports(device["ip"], device["web_url"], device["rtsp_url"])
            kwargs["rtsp_port"] = int(scan_metadata.get("recorder_rtsp_port") or configured_rtsp)
        self.channel_scan_future = self.recorder_executor.submit(
            scan_fn,
            device["ip"],
            username,
            secret,
            **kwargs,
        )
        wait.open()
        self.channel_scan_poll_timer.start()

    def poll_recorder_channel_scan(self):
        context = self.channel_scan_context
        future = self.channel_scan_future
        if context is None or future is None:
            self.channel_scan_poll_timer.stop()
            return

        queue = self.channel_scan_progress_queue
        if queue is not None:
            latest = None
            while True:
                try:
                    latest = queue.get_nowait()
                except Empty:
                    break
            if latest is not None:
                context["label"].setText(latest)

        if not future.done():
            return

        self.channel_scan_poll_timer.stop()
        try:
            channels = future.result()
        except Exception as exc:
            self._finish_recorder_channel_scan(error=f"{type(exc).__name__}: {exc}")
        else:
            self._finish_recorder_channel_scan(channels=channels)

    def cancel_recorder_channel_scan(self):
        if self.channel_scan_cancel_event is not None:
            self.channel_scan_cancel_event.set()
        context = self.channel_scan_context
        if context is not None:
            context["label"].setText("Cancelando leitura com segurança…")
            context["cancel"].setEnabled(False)

    def _prune_unavailable_live_sources(self, device_id: int) -> int:
        """Remove stale/aliased channels from active mosaics after revalidation.

        A failed rescan is not retirement evidence. Historically confirmed
        routes stay in their tiles; the existing per-channel recovery bounds
        retries. Only explicitly retired/unconfirmed or deleted rows are pruned.
        """
        removed = 0
        for tile in getattr(self, "video_tiles", []):
            source = tile.source or {}
            if source.get("type") != "channel" or int(source.get("device_id", 0) or 0) != int(device_id):
                continue
            channel = self.db.get_recorder_channel(int(source.get("channel_id", 0) or 0))
            if channel is not None and (bool(channel["available"]) or previously_confirmed(channel)):
                continue
            self.stop_tile_stream(tile)
            tile.clear_source()
            removed += 1
        if removed:
            self.bottom_notice.setText(f"{removed} canal(is) antigo(s) removido(s) do mosaico após revalidação")
            self.save_live_workspace()
        for win in getattr(self, "detached_windows", {}).values():
            try:
                detached_removed = 0
                for tile in getattr(win, "video_tiles", []):
                    source = tile.source or {}
                    if source.get("type") != "channel" or int(source.get("device_id", 0) or 0) != int(device_id):
                        continue
                    channel = self.db.get_recorder_channel(int(source.get("channel_id", 0) or 0))
                    if channel is not None and (bool(channel["available"]) or previously_confirmed(channel)):
                        continue
                    win.stop_tile(tile)
                    tile.clear_source()
                    detached_removed += 1
                win.refresh_sources()
                if detached_removed:
                    win.status.setText(f"{detached_removed} canal(is) antigo(s) removido(s) após revalidação")
                    win.save_state()
            except Exception:
                pass
        return removed

    def _restart_changed_live_sources(self, device_id: int, channel_ids: set[int]):
        """Switch already open tiles to the newly verified route in place."""
        if not channel_ids:
            return
        for tile in getattr(self, "video_tiles", []):
            source = tile.source or {}
            if (source.get("type") == "channel"
                    and int(source.get("device_id", 0) or 0) == int(device_id)
                    and int(source.get("channel_id", 0) or 0) in channel_ids):
                self.apply_source_to_tile(tile, dict(source))
        for win in getattr(self, "detached_windows", {}).values():
            for tile in getattr(win, "video_tiles", []):
                source = tile.source or {}
                if (source.get("type") == "channel"
                        and int(source.get("device_id", 0) or 0) == int(device_id)
                        and int(source.get("channel_id", 0) or 0) in channel_ids):
                    win.apply_source(tile, dict(source))
        if self.selected_video_tile is not None:
            self.refresh_selected_ptz_controls()
            self.refresh_live_inspector_visibility()

    def _finish_recorder_channel_scan(self, channels=None, error=None):
        context = self.channel_scan_context
        if context is None:
            return
        device_id = context["device_id"]
        device = context["device"]
        wait = context["wait"]
        wait.close()

        title = "Leitura de canais"
        message = None
        severity = None

        if not authorize(self,'device_edit',notify=False):
            channels=None;error='ChannelScanCancelled: acesso administrativo encerrado'

        if error is not None:
            if context.get("direct_camera"):
                # A cancelled or transiently failed rescan provides no new
                # evidence that the last verified routes stopped working.
                # Keep those channels and live sessions until a completed scan
                # can replace them or explicitly mark them unavailable.
                self.refresh_all()
            if error.startswith("ChannelScanCancelled:"):
                self.db.add_event(
                    device["site_id"],
                    device_id,
                    "info",
                    "recorder_channels_cancelled",
                    "Leitura de canais cancelada pelo usuário.",
                )
            else:
                friendly = error
                if error.startswith("RtspAuthenticationError:"):
                    detail = error.split(":", 1)[1].strip()
                    friendly = (
                        f"O gravador {device['name'] or device['model'] or device['ip']} respondeu ao RTSP, "
                        "mas a sessão de vídeo não foi autenticada.\n\n"
                        "Confirme no acesso Web deste gravador se a conta informada consegue visualizar um canal ativo. "
                        "Verifique a porta RTSP e as permissões de vídeo. "
                        "Um retorno 401 também pode indicar uma diferença de autenticação do firmware; "
                        "não é prova isolada de senha incorreta. Compare com outro gravador que abriu vídeo no mesmo computador.\n\n"
                        + detail
                    )
                elif error.startswith("RtspCompatibilityError:"):
                    friendly = error.split(":", 1)[1].strip()
                elif error.startswith(("ConnectionError:", "RuntimeError:", "TimeoutError:")):
                    friendly = error.split(":", 1)[1].strip()
                    if context.get("direct_camera"):
                        friendly += "\n\nA leitura não foi concluída; as rotas validadas anteriormente foram preservadas."
                message = friendly
                severity = "warning"
                try:
                    log_dir = data_dir() / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    with (log_dir / "rtsp-diagnostics.log").open("a", encoding="utf-8") as fh:
                        fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] {device['ip']} — {sanitize_log_text(error)}\n")
                except Exception:
                    pass
        else:
            direct_result = channels if isinstance(channels, DirectCameraScanResult) else None
            if direct_result is not None and direct_result.recorder_detected:
                self.db.apply_detected_identity(
                    device_id, manufacturer=direct_result.manufacturer or "Hikvision",
                    model=direct_result.model, kind="dvr", provider="hikvision",
                    firmware=direct_result.firmware, confidence=95,
                )
                if direct_result.recorder_channel_hint:
                    self.db.merge_device_metadata(device_id, {
                        "channel_scan_limit": direct_result.recorder_channel_hint,
                        "channel_scan_source": "isapi",
                    })
                self.db.add_event(device["site_id"], device_id, "info", "recorder_identity_confirmed",
                                  "Identidade de gravador Hikvision confirmada; iniciando inventário de canais.")
                self.channels_button.setEnabled(True)
                self.channel_scan_context = None
                self.channel_scan_cancel_event = None
                self.channel_scan_future = None
                self.channel_scan_progress_queue = None
                self.channel_scan_worker = None
                self._resume_monitor_after_recorder()
                self.refresh_all()
                credentials = self._credentials_for_device(device_id)
                if credentials:
                    QTimer.singleShot(0, lambda did=device_id, auth=credentials:
                                      self._start_recorder_channel_scan(did, self.db.get_device(did), *auth))
                return
            inventory_notice = getattr(channels, 'notice', '')
            inventory_preserved = bool(getattr(channels, 'preserve_existing', False))
            inventory_identity = getattr(channels, 'identity', None)
            if inventory_identity is not None:
                self.db.apply_detected_identity(device_id,
                    manufacturer=inventory_identity.manufacturer or device['manufacturer'],
                    model=inventory_identity.model, firmware=inventory_identity.firmware,
                    kind=device['kind'], provider=device['provider'])
            raw_channels = direct_result.channels if direct_result is not None else (channels or [])
            partial = bool(getattr(channels, "partial", False))
            available = [ch for ch in raw_channels if ch.available]
            # Direct cameras only keep validated streams operationally. Recorders
            # preserve their physical/IP channel inventory even when a channel is
            # currently sem sinal/offline, so Configuration can explain the DVR
            # state while Live View keeps the known channel inventory visible.
            persisted_rows = available if direct_result is not None else raw_channels
            previous_routes = self.db.list_recorder_channels(device_id) if direct_result is not None else []
            # A completed remote scan with no confirmed video can reflect a
            # temporary VPN outage. Keep the last known inventory for the
            # reconnecting Live View instead of erasing it on that evidence.
            remote_snapshot_preserved = direct_result is None and not partial and preserve_remote_inventory(
                bool(context.get("remote_recorder")), self.db.list_recorder_channels(device_id), raw_channels
            )
            revalidation_states = {}
            if direct_result is not None:
                revalidation_states = self.db.reconcile_direct_camera_channels(
                    device_id, persisted_rows, diagnostics=direct_result.diagnostics,
                )
                try:
                    log_dir = data_dir() / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    with (log_dir / "rtsp-diagnostics.log").open("a", encoding="utf-8") as fh:
                        for item in direct_result.diagnostics:
                            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] {diagnostic_line(item)}\n")
                        for number, state in revalidation_states.items():
                            fh.write(f"Posição {number} • decisão final={state['state']} • motivo={state['reason']}\n")
                except OSError:
                    pass
            elif not remote_snapshot_preserved and not inventory_preserved:
                self.db.replace_recorder_channels(device_id, persisted_rows, partial=partial)
            if direct_result is not None:
                changed_routes = changed_channel_routes(previous_routes, self.db.list_recorder_channels(device_id))
                self._prune_unavailable_live_sources(device_id)
                self._restart_changed_live_sources(device_id, changed_routes)
                self.db.apply_detected_identity(
                    device_id,
                    manufacturer=direct_result.manufacturer,
                    model=direct_result.model,
                    kind="camera",
                    provider=(
                        "intelbras-mibo"
                        if direct_result.manufacturer.lower() == "intelbras"
                        and any(token in direct_result.model.lower() for token in ("im", "mibo"))
                        else device["provider"]
                    ),
                    firmware=direct_result.firmware,
                    serial=direct_result.serial,
                    confidence=90 if (direct_result.manufacturer or direct_result.model) else None,
                )
                event_type = "direct_camera_stream_validated"
                message_text = f"{len(available)} stream(s) direto(s) de câmera IP validado(s) antes do Live View."
            else:
                event_type = "recorder_channels_read"
                message_text = f"{len(raw_channels)} posição(ões) listadas; {len(available)} com mídia validada."
                if partial:
                    event_type = "recorder_channels_partial"
                    message_text += (
                        f" Tempo da leitura encerrado: {int(getattr(channels, 'untested', 0))} posição(ões) "
                        "ainda sem teste RTSP; rotas anteriores preservadas."
                    )
                if inventory_notice:
                    message_text = inventory_notice
                if remote_snapshot_preserved:
                    event_type = "remote_recorder_scan_unconfirmed"
                    message_text = "Leitura remota sem vídeo confirmado; inventário anterior preservado para reconexão."
            self.db.add_event(device["site_id"], device_id, "info", event_type, message_text)
            self.refresh_all()

        # Release scan state before presenting any follow-up dialog. This avoids
        # re-entrancy and stale Qt/Python wrappers if the user interacts quickly.
        self.channels_button.setEnabled(True)
        self.channel_scan_context = None
        self.channel_scan_cancel_event = None
        self.channel_scan_future = None
        self.channel_scan_progress_queue = None
        self.channel_scan_worker = None
        self._resume_monitor_after_recorder()

        if error is None:
            rows = self.db.list_recorder_channels(device_id)
            device = self.db.get_device(device_id) or device
            notice = inventory_notice
            if not notice and remote_snapshot_preserved:
                notice = "Leitura remota sem vídeo confirmado. Exibindo o último inventário conhecido; verifique a conexão e tente novamente."
            elif not notice and partial:
                notice = "Validação parcial: posições restantes ainda precisam de RTSP; canais com vídeo anterior foram preservados."
            self.show_channel_rows(
                device, rows,
                notice=notice,
            )
        elif message:
            box = QMessageBox(self)
            box.setWindowTitle(title)
            box.setIcon(QMessageBox.Warning if severity == "warning" else QMessageBox.Information)
            box.setText(message)
            box.setStandardButtons(QMessageBox.Ok)
            box.setModal(True)
            box.open()
            # Parent ownership keeps the message box valid; WA_DeleteOnClose
            # lets Qt release it after the user dismisses it.
            box.setAttribute(Qt.WA_DeleteOnClose, True)

    def show_saved_channels(self):
        device_id = self.selected_device_id()
        if not device_id:
            return
        device = self.db.get_device(device_id)
        self.show_channel_rows(device, self.db.list_recorder_channels(device_id))

    def show_channel_rows(self, device, rows, *, notice: str = ""):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Canais — {device['name']}")
        dialog.resize(1120, 560)
        layout = QVBoxLayout(dialog)
        try:
            revalidation = json.loads(device["metadata_json"] or "{}").get("direct_channel_revalidation", {})
        except (TypeError, ValueError):
            revalidation = {}
        revalidation = revalidation if isinstance(revalidation, dict) else {}
        retained_count = sum(value.get("state") in {"pending_revalidation", "temporarily_unavailable"} for value in revalidation.values() if isinstance(value, dict))
        fresh_count = sum(value.get("state") == "validated" for value in revalidation.values() if isinstance(value, dict))
        media_count = (f"{fresh_count} com mídia validada nesta leitura • {retained_count} anteriormente confirmado(s), pendente(s) de revalidação" if retained_count else f"{sum(bool(row['available']) for row in rows)} com mídia validada")
        pending_count = sum("ainda não testado" in str(row["detail"] or "").casefold() for row in rows)
        info = QLabel(
            f"{device['name']} • {device['ip']} • {len(rows)} posição(ões) listadas • "
            f"{media_count}"
            + (f" • {pending_count} aguardando RTSP" if pending_count else "") + "\n"
            "Canais sem sinal/offline permanecem visíveis aqui para diagnóstico, mas somente streams validados entram no mosaico Ao vivo."
            + (f"\n{notice}" if notice else "")
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        table = QTableWidget(len(rows), 11)
        table.setHorizontalHeaderLabels([
            "Canal", "Nome do gravador", "Nome no Sentinel", "Saúde", "IP no gravador", "Protocolo",
            "Preferência", "Áudio", "Main stream", "Substream", "Evidência"
        ])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(10, QHeaderView.Stretch)
        for r, ch in enumerate(rows):
            source_name = ch["source_name"] or ch["name"] or f"Canal {ch['channel_no']:02d}"
            display_name = self.db.channel_display_name(ch)
            audio_info = channel_audio_info(device, ch)
            if audio_info["can_talk"]:
                audio_text = "Bidirecional"
            elif audio_info["can_listen"]:
                audio_text = "Escuta • retorno pendente" if audio_info["mode"] == "bidirectional" else "Escuta"
            else:
                audio_text = "—"
            if audio_info.get("codec"):
                audio_text += f" • {audio_info['codec']}"
            source_endpoint = str(ch["source_ip"] or "") if "source_ip" in ch.keys() else ""
            if source_endpoint and "source_port" in ch.keys() and int(ch["source_port"] or 0):
                source_endpoint += f":{int(ch['source_port'])}"
            source_protocol = str(ch["source_protocol"] or "") if "source_protocol" in ch.keys() else ""
            vals = (
                ch["channel_no"], source_name, display_name,
                channel_health_label(ch, device_online=str(device["status"] or "") == "online"),
                source_endpoint or "—", source_protocol or "—", ch["preferred_stream"], audio_text,
                ch["main_rtsp_url"] or ch["rtsp_url"], ch["sub_rtsp_url"] or "—",
                ch["detail"] + (" • Pendente de revalidação; identidade anterior preservada" if revalidation.get(str(ch["channel_no"]), {}).get("state") in {"pending_revalidation", "temporarily_unavailable"} else ""),
            )
            for c, value in enumerate(vals):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        if rows:
            media_diagnose = QPushButton("Diagnosticar mídia Main/Sub")
            media_diagnose.clicked.connect(lambda: self.show_channel_stream_diagnostics(device, rows))
            layout.addWidget(media_diagnose, 0, Qt.AlignLeft)
        if recorder_provider_hint(device) in ("hikvision", "jfl") and rows:
            diagnose = QPushButton("Diagnosticar Main/Sub")
            diagnose.setToolTip("Testar as duas rotas RTSP de cada canal sem alterar o gravador")
            diagnose.clicked.connect(lambda: self.diagnose_hikvision_channel_routes(device, rows))
            layout.addWidget(diagnose, 0, Qt.AlignLeft)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.setModal(True)
        self._transient_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0, d=dialog: self._release_transient_dialog(d))
        dialog.open()

    def diagnose_selected_streams(self):
        tile = self.selected_video_tile
        if not tile or not tile.source or tile.source.get("type") != "channel":
            return
        device = self.db.get_device(int(tile.source["device_id"]))
        channel = self.db.get_recorder_channel(int(tile.source["channel_id"]))
        if device and channel and int(channel["device_id"]) == int(device["id"]):
            self.show_channel_stream_diagnostics(device, [channel])

    def show_channel_stream_diagnostics(self, device, rows):
        credentials = self._credentials_for_device(int(device["id"])) or ("", "")
        # Saved rows/credentials are captured before starting the worker. Changing
        # Site or selection never rebinds this diagnostic or writes its results.
        channels = [dict(row) for row in rows]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Diagnóstico Main/Sub — {device['name']}")
        dialog.resize(880, 520)
        layout = QVBoxLayout(dialog)
        status = QLabel("Verificando as rotas cadastradas; sem alterar o equipamento…")
        status.setWordWrap(True)
        layout.addWidget(status)
        table = QTableWidget(0, 4)
        table.setObjectName("streamDiagnosticsTable")
        table.setHorizontalHeaderLabels(["Canal", "Stream", "Resultado", "Vídeo / áudio / codecs"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(table)
        cancel_event = Event()
        completed = [False]
        report_lines = []
        copy = QPushButton("Copiar diagnóstico")
        copy.setEnabled(False)
        copy.clicked.connect(lambda: QApplication.clipboard().setText("\n".join(report_lines)))
        layout.addWidget(copy, 0, Qt.AlignLeft)
        close = QPushButton("Cancelar teste")
        close.clicked.connect(lambda: dialog.accept() if completed[0] else cancel_event.set())
        layout.addWidget(close, 0, Qt.AlignRight)
        worker = Worker(diagnose_saved_streams, channels, *credentials, cancel_event=cancel_event, with_progress=True)
        worker.signals.progress.connect(status.setText)
        def show_results(results):
            if not dialog.isVisible():
                return
            table.setRowCount(len(results))
            report_lines.clear()
            for index, result in enumerate(results):
                values = (result.channel_no, result.stream, STREAM_STATE_LABELS.get(result.state, "Inconclusivo"), result.summary())
                report_lines.append(" • ".join(str(value) for value in values))
                for col, value in enumerate(values):
                    table.setItem(index, col, QTableWidgetItem(str(value)))
            copy.setEnabled(bool(results))
            status.setText(f"{len(results)} rota(s) verificada(s)" + (" • cancelado" if cancel_event.is_set() else ""))
        worker.signals.result.connect(show_results)
        worker.signals.error.connect(lambda _error: status.setText("Falha na verificação de mídia; sem alterar o cadastro."))
        worker.signals.finished.connect(lambda: completed.__setitem__(0, True))
        worker.signals.finished.connect(lambda: close.setText("Fechar") if dialog.isVisible() else None)
        dialog.finished.connect(lambda _result: cancel_event.set())
        self._transient_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0: self._release_transient_dialog(dialog) if completed[0] else None)
        worker.signals.finished.connect(lambda: self._release_transient_dialog(dialog) if not dialog.isVisible() else None)
        dialog.open()
        self.start_qt_worker(worker)

    def diagnose_hikvision_channel_routes(self, device, rows):
        credentials = self._credentials_for_device(int(device["id"]))
        if not credentials:
            QMessageBox.information(self, "Diagnóstico RTSP", "Salve ou informe a credencial do gravador antes do teste.")
            return
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        _web_port, configured_rtsp = forwarded_ports(device["ip"], device["web_url"], device["rtsp_url"])
        port = int(metadata.get("recorder_rtsp_port") or configured_rtsp)
        channel_numbers = [int(row["channel_no"]) for row in rows]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Diagnóstico Main/Sub — {device['name']}")
        dialog.resize(900, 620)
        layout = QVBoxLayout(dialog)
        status = QLabel(f"Testando {len(channel_numbers)} canais na porta RTSP {port}…")
        layout.addWidget(status)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Canal", "Stream", "Resultado", "Resposta RTSP"])
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(table)
        cancel_event = Event()
        report_lines = []
        copy = QPushButton("Copiar diagnóstico")
        copy.setEnabled(False)
        copy.clicked.connect(lambda: QApplication.clipboard().setText("\n".join(report_lines)))
        layout.addWidget(copy, 0, Qt.AlignLeft)
        close = QPushButton("Cancelar teste")
        completed = [False]
        close.clicked.connect(lambda: dialog.accept() if completed[0] else cancel_event.set())
        layout.addWidget(close, 0, Qt.AlignRight)
        worker = Worker(diagnose_hikvision_routes, device["ip"], credentials[0], credentials[1],
                        channel_numbers, rtsp_port=port, cancel_event=cancel_event, with_progress=True)
        worker.signals.progress.connect(status.setText)
        def show_results(results):
            if not dialog.isVisible():
                return
            table.setRowCount(len(results))
            for index, values in enumerate(results):
                for col, value in enumerate(values):
                    table.setItem(index, col, QTableWidgetItem(str(value)))
            report_lines[:] = [f"Hikvision • porta RTSP {port} • {len(results) // 2} canais"] + [
                f"Canal {channel} • {stream} • {state} • {detail}"
                for channel, stream, state, detail in results
            ]
            copy.setEnabled(True)
            status.setText(f"{len(results) // 2} canal(is) testado(s) • porta {port} • sem alterar o DVR")
        worker.signals.result.connect(show_results)
        worker.signals.error.connect(status.setText)
        worker.signals.finished.connect(lambda: completed.__setitem__(0, True))
        worker.signals.finished.connect(lambda: close.setText("Fechar") if dialog.isVisible() else None)
        dialog.finished.connect(lambda _result: cancel_event.set())
        self._transient_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0, d=dialog: self._release_transient_dialog(d) if completed[0] else None)
        worker.signals.finished.connect(lambda: self._release_transient_dialog(dialog) if not dialog.isVisible() else None)
        dialog.open()
        self.start_qt_worker(worker)

    def _release_transient_dialog(self, dialog):
        try:
            self._transient_dialogs.remove(dialog)
        except ValueError:
            pass
        dialog.deleteLater()

    # ---------- monitoring ----------
    def monitor_tick(self):
        devices = self.db.list_devices(self.current_site_id)
        for device in devices:
            if is_cloud_device(device):
                # A serial is not a DNS/LAN target; idle devices have no
                # background credential retries. Observe actual decoded video.
                active = False
                for owner in (self, *self.detached_windows.values()):
                    sessions = owner.live_sessions if owner is self else owner.sessions
                    for tile in owner.video_tiles:
                        source = tile.source or {}
                        session = sessions.get(tile.index)
                        if (source.get("device_id") == device["id"] and session is not None
                                and session.last_frame_at is not None
                                and time.monotonic() - session.last_frame_at < 30):
                            active = True
                self.db.update_device_status(device["id"], "online" if active else "unknown")
                continue
            endpoints = [dict(row) for row in self.db.list_device_endpoints(int(device["id"]))]
            worker = Worker(
                diagnose_endpoints, endpoints, device["ip"], device["web_url"], device["rtsp_url"]
            )
            worker.signals.result.connect(lambda result, did=device["id"]: self.monitor_result(did, result))
            self.start_qt_worker(worker)

    def monitor_result(self, device_id, result):
        status = "online" if result.online else "offline"
        self.db.update_device_status(device_id, status)
        for ip, endpoint_status in getattr(result, "endpoint_statuses", {}).items():
            self.db.update_endpoint_status(device_id, ip, endpoint_status)
        self.db.add_observation(device_id, status, result.latency_ms, result.rtsp_ok, result.web_ok)
        if status == "online":
            self.start_channel_health_check(int(device_id))
        self.refresh_all()

    def start_channel_health_check(self, device_id: int):
        """Start one bounded read-only health pass for saved recorder channels."""
        device_id = int(device_id)
        if device_id in self.channel_health_inflight:
            return
        # The 30-second recorder heartbeat must not launch a full RTSP probe
        # for every saved channel on every tick.  A 16-channel recorder could
        # otherwise generate 16 new media handshakes every 30 seconds.
        now = time.monotonic()
        if now - self.channel_health_last_started.get(device_id, float('-inf')) < 120:
            return
        device = self.db.get_device(device_id)
        if is_cloud_device(device):
            return
        if not device or str(device["status"] or "") != "online":
            return
        channels = [dict(row) for row in self.db.list_recorder_channels(device_id)]
        if not channels:
            return
        credentials = self._credentials_for_device(device_id)
        if not credentials:
            return
        username, password = credentials
        self.channel_health_inflight.add(device_id)
        self.channel_health_last_started[device_id] = now
        worker = Worker(
            probe_recorder_channel_health,
            str(device["provider"] or "generic"), str(device["ip"] or ""), username, password, channels,
        )
        worker.signals.result.connect(lambda samples, did=device_id: self.channel_health_result(did, samples))
        worker.signals.error.connect(lambda error, did=device_id: self.channel_health_error(did, error))
        worker.signals.finished.connect(lambda did=device_id: self.channel_health_inflight.discard(did))
        self.start_qt_worker(worker)

    def channel_health_result(self, device_id: int, samples):
        device = self.db.get_device(int(device_id))
        # If the recorder went offline while the channel probe was running, do
        # not fan one recorder outage out into many channel-loss alerts.
        if not device or str(device["status"] or "") != "online":
            return
        self.db.apply_channel_health_samples(int(device_id), samples, failure_threshold=2)
        self.refresh_all()

    def channel_health_error(self, device_id: int, error: str):
        device = self.db.get_device(int(device_id))
        if device:
            self.bottom_notice.setText(f"Saúde de canais: {device['name']} não pôde ser verificado agora")


    def show_release_notes_if_needed(self):
        pending = data_dir() / "pending-release-notes.json"
        state_path = data_dir() / "release-state.json"
        try:
            pending_data = json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else {}
        except Exception:
            pending_data = {}
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except Exception:
            state = {}
        if pending_data.get("version") != __version__:
            return
        if state.get("last_shown_version") == __version__:
            try: pending.unlink(missing_ok=True)
            except Exception: pass
            return
        previous = pending_data.get("previous_version") or "versão anterior"
        box = QMessageBox(self)
        box.setWindowTitle("Novidades desta versão")
        box.setIcon(QMessageBox.Information)
        box.setText(f"Artin Sentinel atualizado\n{previous} → {__version__}\n\n{RELEASE_TITLE}")
        box.setInformativeText("\n".join(f"• {item}" for item in RELEASE_NOTES))
        changelog = box.addButton("Ver changelog", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        def finished(_result=0):
            state_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                state_path.write_text(json.dumps({"last_shown_version": __version__}, ensure_ascii=False), encoding="utf-8")
                pending.unlink(missing_ok=True)
            except Exception:
                pass
        def clicked(button):
            if button is changelog:
                detail = QMessageBox(self)
                detail.setWindowTitle(f"Changelog — {__version__}")
                detail.setText(CHANGELOG_TEXT)
                detail.setStandardButtons(QMessageBox.Close)
                detail.setModal(True)
                detail.open()
                self._transient_dialogs.append(detail)
                detail.finished.connect(lambda _=0, d=detail: self._release_transient_dialog(d))
        box.buttonClicked.connect(clicked)
        box.finished.connect(finished)
        box.setModal(True)
        box.open()
        self._transient_dialogs.append(box)
        box.finished.connect(lambda _=0, d=box: self._release_transient_dialog(d))

    def closeEvent(self, event):
        if not password_dialog(self.app_auth, "Sair do Sentinel", "Digite a senha para sair:", parent=self):
            event.ignore()
            return
        shutdown_sessions = list(self.live_sessions.values()) + [
            self.live_audio_session, self.talkback_session,
            getattr(self, "_live_audio_previous_session", None),
            self.playback_session, self.playback_audio_session,
        ]
        shutdown_sessions.extend(self.playback_sessions.values())
        for window in self.detached_windows.values():
            shutdown_sessions.extend(window.sessions.values())
            shutdown_sessions.extend([window.audio_session, getattr(window, "_previous_audio_session", None)])
        shutdown_sessions = media_session_chain(shutdown_sessions)
        self._closing_app = True
        cloud_dialog = getattr(self, "_cloud_bridge_dialog", None)
        if cloud_dialog is not None:
            cloud_dialog.reject()
        runtime_panel = getattr(self, "_runtime_panel", None)
        if runtime_panel is not None: runtime_panel.reject()
        pc_dialog = getattr(self, "_pc_analysis_dialog", None)
        if pc_dialog is not None: pc_dialog.reject()
        history_dialog = getattr(self, "_recording_history_dialog", None)
        if history_dialog is not None:
            history_dialog.reject()
        self.stop_camera_events()
        self.save_live_workspace()
        if self.manual_recording is not None:
            self.manual_recording.stop()
            self.manual_recording._thread.join(timeout=12)
        if self.playback_export_cancel is not None:
            self.playback_export_cancel.set()
        self.playback_poll_timer.stop()
        if hasattr(self, "playback_day_search_timer"): self.playback_day_search_timer.stop()
        self.stop_playback_stream()
        self._closing_app = True
        for win in list(self.detached_windows.values()):
            try: win.close()
            except Exception: pass
        self.detached_windows.clear()
        if self.channel_scan_cancel_event is not None:
            self.channel_scan_cancel_event.set()
        self.channel_scan_poll_timer.stop()
        self.live_poll_timer.stop()
        self.ptz_poll_timer.stop()
        self.monitor.stop()
        self.stop_all_live_streams()
        self.performance_timer.stop()
        if getattr(self, "_ui_heartbeat", None) is not None: self._ui_heartbeat.stop()
        self.discovery_clock.stop()
        wait_media_sessions(shutdown_sessions, timeout=4.0)
        from .playback_session_pool import shutdown_playback_pool
        shutdown_playback_pool()
        from .intelbras_wine import shutdown_wine
        shutdown_wine()
        self.recorder_executor.shutdown(wait=False, cancel_futures=True)
        self.ptz_executor.shutdown(wait=False, cancel_futures=False)
        self.audio_executor.shutdown(wait=False, cancel_futures=True)
        self.db.close()
        super().closeEvent(event)

    @requires_permission('admin')
    def change_app_password(self):
        if not password_dialog(self.app_auth, "Alterar senha", "Digite a senha atual:", parent=self):
            return
        if create_password_dialog(self.app_auth, parent=self):
            QMessageBox.information(self, "Acesso", "Senha de acesso alterada.")


def password_dialog(auth: AppAuth, title: str, prompt: str, parent=None) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(prompt))
    password = QLineEdit()
    password.setEchoMode(QLineEdit.Password)
    password.setPlaceholderText("Senha de acesso")
    layout.addWidget(password)
    warning = QLabel("")
    warning.setStyleSheet("color:#ff9b87")
    layout.addWidget(warning)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Entrar" if title == "Entrar no Sentinel" else "Confirmar")
    buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
    layout.addWidget(buttons)
    failures = [0]
    blocked_until = [0.0]
    def submit():
        if time.monotonic() < blocked_until[0]:
            warning.setText("Aguarde 30 segundos antes de tentar novamente.")
            return
        if auth.verify(password.text()):
            dialog.accept()
        else:
            failures[0] += 1
            warning.setText("Senha incorreta. Tente novamente.")
            password.clear()
            if failures[0] >= 5:
                buttons.button(QDialogButtonBox.Ok).setEnabled(False)
                blocked_until[0] = time.monotonic() + 30
                QTimer.singleShot(30_000, lambda: buttons.button(QDialogButtonBox.Ok).setEnabled(True))
                failures[0] = 0
    buttons.accepted.connect(submit)
    buttons.rejected.connect(dialog.reject)
    password.returnPressed.connect(submit)
    password.setFocus()
    return dialog.exec() == QDialog.Accepted


def create_password_dialog(auth: AppAuth, parent=None) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Criar senha do Sentinel")
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Crie uma senha local (mínimo de 4 caracteres). Guarde-a em local seguro."))
    first = QLineEdit()
    confirm = QLineEdit()
    for edit, hint in ((first, "Nova senha"), (confirm, "Confirme a senha")):
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText(hint)
        layout.addWidget(edit)
    warning = QLabel("")
    warning.setStyleSheet("color:#ff9b87")
    layout.addWidget(warning)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Salvar senha")
    layout.addWidget(buttons)
    def submit():
        if first.text() != confirm.text():
            warning.setText("As senhas não coincidem.")
            return
        try:
            auth.set_password(first.text())
        except (OSError, ValueError) as exc:
            warning.setText(f"Não foi possível salvar: {exc}")
            return
        dialog.accept()
    buttons.accepted.connect(submit)
    buttons.rejected.connect(dialog.reject)
    first.setFocus()
    return dialog.exec() == QDialog.Accepted


def main():
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fault_path = log_dir / "native-fault.log"
    fault_file = open(fault_path, "a", buffering=1, encoding="utf-8")
    fault_file.write(f"\n--- Artin Sentinel {__version__} start {datetime.now().isoformat()} ---\n")
    faulthandler.enable(file=fault_file, all_threads=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Artin Sentinel")
    app.setDesktopFileName("artin-sentinel")
    app.setWindowIcon(QIcon(resource_path("artin-sentinel.png")))
    app.setStyleSheet(QSS)
    auth = AppAuth(data_dir() / "access.json")
    if not (password_dialog(auth, "Entrar no Sentinel", "Digite a senha para entrar:")
            if auth.configured else create_password_dialog(auth)):
        faulthandler.disable()
        fault_file.close()
        return
    window = MainWindow()
    window.show()
    QTimer.singleShot(350, window.show_release_notes_if_needed)
    QTimer.singleShot(5000, window.check_for_updates_startup)
    try:
        code = app.exec()
    finally:
        faulthandler.disable()
        fault_file.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
