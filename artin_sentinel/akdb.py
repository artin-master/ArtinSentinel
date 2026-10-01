from __future__ import annotations

"""AKDB — conservative, credential-free device/protocol knowledge.

0.2.15 keeps Sentinel-specific capability mapping as a domain extension over
the shared Artin AKDB Core. A capability/type is only advertised when the
profile actually says so; model-specific knowledge is never projected onto
every device from the same manufacturer/provider.
"""

from dataclasses import dataclass, replace
import json
import re
import sqlite3
from typing import Iterable

from artin_akdb import record_by_legacy_key, default_store_path


@dataclass(frozen=True, slots=True)
class AkdbProfile:
    key: str
    manufacturer: str
    canonical_type: str
    family: str = ""
    device_types: tuple[str, ...] = ()
    ports_any: tuple[int, ...] = ()
    text_tokens: tuple[str, ...] = ()
    required_tokens: tuple[str, ...] = ()
    provider: str = "generic"
    protocol_family: str = "generic"
    rtsp_main: str = ""
    rtsp_sub: str = ""
    notes: tuple[str, ...] = ()
    validation: str = "detected"
    confidence_floor: int = 0
    compatible_with: tuple[str, ...] = ()
    audio_mode: str = "unknown"
    audio_codecs: tuple[str, ...] = ()
    talkback_protocol: str = ""
    talkback_scope: str = "all"
    talkback_validation: str = "unknown"
    ptz_mode: str = "unknown"
    ptz_scope: str = "all"
    lens_count: int = 0
    features: tuple[str, ...] = ()
    # Normalized capability/type knowledge.
    stream_count: int = 0
    video_codecs: tuple[str, ...] = ()
    onvif_profiles: tuple[str, ...] = ()
    native_protocols: tuple[str, ...] = ()
    max_analog_channels: int = 0
    max_ip_channels: int = 0
    max_total_channels: int = 0


PROFILES: tuple[AkdbProfile, ...] = (
    AkdbProfile(
        key="intelbras-vipc-1230-d-g2",
        manufacturer="Intelbras",
        canonical_type="camera-fixed",
        family="VIPC 1230 D G2",
        device_types=("camera",),
        text_tokens=("vipc 1230 d g2", "vipc-1230-d-g2", "vipc1230dg2"),
        required_tokens=("vipc 1230 d g2", "vipc-1230-d-g2", "vipc1230dg2"),
        provider="intelbras",
        protocol_family="intelbras-ipc-local",
        rtsp_main="/cam/realmonitor?channel=1&subtype=0",
        rtsp_sub="/cam/realmonitor?channel=1&subtype=1",
        notes=(
            "câmera fixa 2 MP; dois streams locais documentados",
            "ONVIF Profile S/T e RTSP; declaração ONVIF do modelo informa PTZ=NO e Audio=NO",
            "CGI/Intelbras pode ser usado futuramente apenas em operações read-only explicitamente validadas",
        ),
        validation="documented",
        confidence_floor=90,
        compatible_with=("onvif", "rtsp", "intelbras-cgi-readonly-candidate"),
        audio_mode="none",
        ptz_mode="none",
        features=("fixed-camera", "motion-detection", "ir", "poe", "dual-stream"),
        stream_count=2,
        video_codecs=("H.264", "H.265", "MJPEG"),
        onvif_profiles=("S", "T"),
        native_protocols=("rtsp", "onvif", "intelbras-cgi-readonly-candidate"),
    ),
    AkdbProfile(
        key="intelbras-nvd-1416", manufacturer="Intelbras", canonical_type="nvr",
        family="NVD 1416", device_types=("nvr",),
        text_tokens=("nvd 1416", "nvd1416"), required_tokens=("nvd 1416", "nvd1416"),
        provider="intelbras", protocol_family="dahua-intelbras", max_total_channels=16,
        validation="field-detected", confidence_floor=90,
        notes=("16 canais mostrados na interface do gravador; RTSP ainda não homologado",),
        native_protocols=("rtsp-candidate", "onvif-candidate"),
    ),
    AkdbProfile(
        key="intelbras-nvd-1516", manufacturer="Intelbras", canonical_type="nvr",
        family="NVD 1516", device_types=("nvr",),
        text_tokens=("nvd 1516", "nvd1516"), required_tokens=("nvd 1516", "nvd1516"),
        provider="intelbras", protocol_family="dahua-intelbras", max_total_channels=16,
        validation="field-detected", confidence_floor=90,
        notes=("16 canais mostrados na interface do gravador; RTSP ainda não homologado",),
        native_protocols=("rtsp-candidate", "onvif-candidate"),
    ),
    AkdbProfile(
        key="intelbras-mhdx-1216", manufacturer="Intelbras", canonical_type="xvr",
        family="MHDX 1216", device_types=("dvr", "xvr"),
        text_tokens=("mhdx 1216", "mhdx1216"), required_tokens=("mhdx 1216", "mhdx1216"),
        provider="intelbras", protocol_family="dahua-intelbras", max_total_channels=16,
        validation="field-detected", confidence_floor=90,
        notes=("16 canais mostrados na interface do gravador; RTSP ainda não homologado",),
        native_protocols=("rtsp-candidate", "onvif-candidate"),
    ),
    AkdbProfile(
        key="intelbras-mhdx",
        manufacturer="Intelbras",
        canonical_type="xvr",
        family="MHDX 1004",
        device_types=("dvr", "xvr"),
        ports_any=(37777,),
        text_tokens=("mhdx 1004", "mhdx1004"),
        required_tokens=("mhdx 1004", "mhdx1004"),
        provider="intelbras",
        protocol_family="dahua-intelbras",
        rtsp_main="/cam/realmonitor?channel={channel}&subtype=0",
        rtsp_sub="/cam/realmonitor?channel={channel}&subtype=1",
        notes=(
            "MHDX 1004: 4 entradas analógicas + 1 canal IP adicional dedicado (canal lógico 5)",
            "enumeração dinâmica; pode expor canais IP além das entradas físicas em outras variantes da família",
            "tentar ChannelTitle CGI somente leitura quando o firmware disponibilizar a interface",
        ),
        validation="field-validated",
        confidence_floor=70,
        max_analog_channels=4,
        max_ip_channels=1,
        features=("hybrid-recorder", "ip-extra-channel"),
        native_protocols=("rtsp", "intelbras-dahua-cgi-readonly-candidate", "onvif-candidate"),
    ),
    AkdbProfile(
        key="intelbras-imx-c",
        manufacturer="Intelbras",
        canonical_type="camera-consumer",
        family="Mibo iMX C",
        device_types=("camera",),
        text_tokens=("imx c", "imx-c", "imx_c"),
        required_tokens=("imx c", "imx-c", "imx_c"),
        provider="intelbras-mibo",
        protocol_family="intelbras-mibo-local",
        notes=(
            "iMX C identificada em campo: Live View e áudio de escuta validados no Sentinel",
            "documentação do fabricante declara RTSP, ONVIF, Intelbras-1, áudio bidirecional e compressão AAC",
            "áudio bidirecional do hardware não implica backchannel ONVIF/RTSP; retorno local permanece candidato Intelbras-1 até homologação",
            "não expor MIC operacional enquanto não existir transporte de retorno específico validado por firmware",
        ),
        validation="field-validated",
        confidence_floor=92,
        compatible_with=("rtsp", "onvif", "intelbras-1-candidate"),
        audio_mode="bidirectional",
        audio_codecs=("AAC",),
        talkback_protocol="intelbras-1-candidate",
        talkback_scope="primary",
        talkback_validation="candidate",
        features=("consumer-camera", "listen-audio", "bidirectional-audio-hardware"),
        native_protocols=("rtsp", "onvif", "intelbras-1-candidate"),
    ),
    AkdbProfile(
        key="intelbras-mibo",
        manufacturer="Intelbras",
        canonical_type="camera-consumer",
        family="MiboCam",
        device_types=("camera",),
        text_tokens=("mibo", "mibocam"),
        provider="intelbras-mibo",
        protocol_family="onvif-rtsp",
        notes=(
            "não assumir interface web; validar ONVIF/RTSP diretamente",
            "teste de campo: vídeo e áudio de escuta funcionais; retorno/talkback local continua sem transporte homologado",
        ),
        validation="field-detected",
        confidence_floor=65,
        audio_mode="bidirectional",
        audio_codecs=("unknown",),
        talkback_protocol="unvalidated",
        talkback_scope="primary",
        talkback_validation="unvalidated",
        native_protocols=("onvif", "rtsp"),
    ),
    AkdbProfile(
        key="hikvision-ds-7216hghi-f1",
        manufacturer="Hikvision",
        canonical_type="dvr",
        family="DS-7216HGHI-F1",
        device_types=("xvr", "dvr"),
        ports_any=(8000,),
        text_tokens=("ds-7216hghi-f1", "ds 7216hghi f1", "7216hghi"),
        required_tokens=("ds-7216hghi-f1", "ds 7216hghi f1", "7216hghi"),
        provider="hikvision",
        protocol_family="hikvision-turbohd",
        rtsp_main="/Streaming/Channels/{channel}01",
        rtsp_sub="/Streaming/Channels/{channel}02",
        notes=(
            "Turbo HD DVR com 16 entradas analógicas e até 2 canais IP adicionais conforme documentação da família/modelo",
            "dual stream; RTSP Hikvision /Streaming/Channels/{canal}01/02",
            "porta 8000/ISAPI são candidatos de integração local; qualquer consulta nativa deve permanecer read-only",
            "teste de campo V4.30.122 build 201107: deviceType=IPC não deve substituir o modelo exato DS-7216HGHI-F1; Video/inputs/channels listou 16 entradas e InputProxy/status revelou canal IP 17 configurado",
        ),
        validation="field-validated",
        confidence_floor=92,
        compatible_with=("rtsp", "hikvision-service-8000", "hikvision-isapi-readonly-candidate", "onvif-candidate"),
        audio_mode="unknown",  # device audio I/O must not be projected to every channel
        ptz_mode="recorder-mediated",
        features=("dual-stream", "coaxitron-ptz-recorder", "smart-search", "vca", "hybrid-recorder"),
        stream_count=2,
        video_codecs=("H.264", "H.264+"),
        native_protocols=("rtsp", "hikvision-service-8000", "hikvision-isapi-readonly-candidate"),
        max_analog_channels=16,
        max_ip_channels=2,
    ),
    AkdbProfile(
        key="hikvision-generic",
        manufacturer="Hikvision",
        canonical_type="unknown",
        family="Hikvision",
        device_types=("camera", "dvr", "nvr", "xvr"),
        ports_any=(8000,),
        text_tokens=("hikvision", "dvrdvs-webs", "hikvision-webs"),
        provider="hikvision",
        protocol_family="hikvision",
        rtsp_main="/Streaming/Channels/{channel}01",
        rtsp_sub="/Streaming/Channels/{channel}02",
        notes=("porta 8000 é evidência forte, mas deve ser combinada com outras evidências",),
        validation="tested",
        confidence_floor=60,
        compatible_with=("onvif", "rtsp", "hikvision-service-8000", "hikvision-isapi-readonly-candidate"),
        native_protocols=("rtsp", "onvif-candidate", "hikvision-service-8000", "hikvision-isapi-readonly-candidate"),
    ),
    AkdbProfile(
        key="jfl-hikvision-compatible",
        manufacturer="JFL",
        canonical_type="unknown",
        family="",
        device_types=("camera", "dvr", "nvr"),
        text_tokens=("jfl",),
        provider="jfl",
        protocol_family="hikvision-compatible",
        rtsp_main="/Streaming/Channels/{channel}01",
        rtsp_sub="/Streaming/Channels/{channel}02",
        notes=("compatibilidade Hikvision deve ser validada por modelo/firmware; manter fabricante JFL",),
        validation="detected",
        confidence_floor=55,
        compatible_with=("hikvision-rtsp-candidate", "onvif"),
        native_protocols=("hikvision-rtsp-candidate", "onvif-candidate"),
    ),
    AkdbProfile(
        key="aitek-sigma-seg6050bp",
        manufacturer="Aitek",
        canonical_type="camera-fixed",
        family="SIGMA",
        device_types=("camera",),
        text_tokens=("aitek", "sigma-seg6050bp"),
        provider="aitek",
        protocol_family="onvif-rtsp-local",
        rtsp_main="/live/0/MAIN",
        rtsp_sub="/live/0/SUB",
        notes=(
            "modelo comercial SIGMA-SEG6050BP; plataforma/firmware reporta H2-52PGX",
            "um canal real; Main 5MP e Sub 800x448 observados em campo",
            "priorizar acesso LAN RTSP/ONVIF; P2P/cloud fora do escopo atual",
        ),
        validation="field-validated",
        confidence_floor=80,
        compatible_with=("onvif", "rtsp", "platform-h2-52pgx"),
        audio_mode="listen",
        audio_codecs=("pcm_mulaw",),
        talkback_protocol="",
        stream_count=2,
        native_protocols=("rtsp", "onvif"),
    ),
    AkdbProfile(
        key="oem-h2-52pgx",
        manufacturer="OEM/XM",
        canonical_type="camera-fixed",
        family="H2-52PGX platform",
        device_types=("camera",),
        text_tokens=("h2-52pgx", "h2 52pgx"),
        required_tokens=("h2-52pgx", "h2 52pgx"),
        provider="generic",
        protocol_family="generic-onvif-rtsp",
        notes=(
            "plataforma H2-52PGX observada em câmeras fixas/bullet; não assumir modelo comercial apenas pelo código da plataforma",
            "tratar como câmera IP e evitar enumeração de gravador; capabilities específicas exigem homologação por variante",
        ),
        validation="field-identified",
        confidence_floor=75,
        compatible_with=("onvif-candidate", "rtsp-candidate", "http-fingerprint"),
        audio_mode="unknown",
        ptz_mode="none",
        features=("fixed-camera",),
        native_protocols=("onvif-candidate", "rtsp-candidate"),
    ),
    AkdbProfile(
        key="aitek-camera",
        manufacturer="Aitek",
        canonical_type="camera-fixed",
        family="",
        device_types=("camera",),
        text_tokens=("aitek",),
        provider="aitek",
        protocol_family="generic-onvif-rtsp",
        notes=("câmera IP simples; não executar enumeração ampla de gravador sem evidência adicional",),
        validation="field-validated",
        confidence_floor=70,
        native_protocols=("rtsp", "onvif-candidate"),
    ),
    AkdbProfile(
        key="it-blue-x3-we2q",
        manufacturer="IT-Blue",
        canonical_type="camera-ptz",
        family="Speed Dome X3-WE2Q",
        device_types=("camera",),
        ports_any=(34567,),
        text_tokens=("x3-we2q", "000a06cd", "xm535d1"),
        required_tokens=("x3-we2q", "000a06cd", "xm535d1"),
        provider="it-blue",
        protocol_family="xm-icsee-local",
        rtsp_main="/user={username}_password={password}_channel=0_stream=0.sdp?real_stream",
        rtsp_sub="/user={username}_password={password}_channel=0_stream=1.sdp?real_stream",
        notes=(
            "Speed Dome IT-Blue identificada em campo como X3-WE2Q; firmware da família V5.02.R02.000A06CD",
            "plataforma OEM correlacionada a XM535D1; acesso LAN deve ser priorizado sobre cloud/P2P",
            "interface do app mostra três visões; o Sentinel testa índices RTSP 0/1/2 e só persiste streams distintos realmente validados",
            "se RTSP expuser apenas a lente principal, as demais permanecem pendentes de transporte XM/DVRIP/34567",
            "PTZ Pan/Tilt por XM/Sofia DVRIP TCP/34567 confirmado em campo; eixo horizontal corrigido no provider",
            "zoom óptico/motorizado não confirmado em campo e não deve ser anunciado como capability homologada",
            "três lentes físicas são conhecidas; somente streams locais visualmente distintos entram no Live View",
            "rastreamento, detecção humana, alarme sonoro/luminoso e áudio full duplex foram observados no app do equipamento",
            "0.2.24: teste físico não confirmou Push-to-Talk; escuta permanece validada.",
            "0.2.28: retorno DVRIP/Sofia G.711 A-law habilitado somente como experimental para teste de campo; não homologado.",
            "0.2.29: OPTalk passa a usar Claim em socket dedicado, Start/Stop no controle e SampleRate=8; continua experimental até teste físico.",
            "0.2.29: quando RTSP expõe apenas a PTZ, OPMonitor DVRIP pode validar as lentes fixas; persistência ocorre somente após mídia H.264/H.265 real e ainda não é homologada.",
            "0.2.30: capacidade de talkback passa a ser separada do modo de áudio observado; MIC experimental é exposto somente na lente principal/PTZ e continua não homologado até validação de campo.",
            "0.2.32: lentes adicionais foram descobertas em campo; capabilities PTZ/MIC não devem ser herdadas pela lente fixa.",
            "0.2.33: PTZ passa a ter escopo por lente; talkback testa fluxo DVRIP em sessão única com diagnóstico por etapas.",
        ),
        validation="field-validated",
        confidence_floor=85,
        compatible_with=("rtsp", "xm-icsee", "onvif-candidate", "xm-dvrip-34567", "xm-dvrip-opmonitor-multilens-experimental"),
        audio_mode="bidirectional",
        audio_codecs=("unknown",),
        talkback_protocol="xm-dvrip-g711a-experimental",
        talkback_scope="primary",
        talkback_validation="experimental",
        ptz_mode="dvrip-confirmed",
        ptz_scope="primary",
        lens_count=3,
        features=("ptz", "multi-lens", "motion-tracking", "human-detection", "siren", "white-light", "multi-view"),
        stream_count=2,
        native_protocols=("rtsp", "onvif-candidate", "xm-dvrip-34567", "xm-dvrip-opmonitor-multilens-experimental"),
    ),
    AkdbProfile(
        key="it-blue-gk7202v300-cloud",
        manufacturer="IT-Blue",
        canonical_type="camera-ptz",
        family="Speed Dome GK7202V300",
        device_types=("camera",),
        text_tokens=("ipc_gk7202v300_lpg-g5-wq", "gk7202v300", "000779su"),
        required_tokens=("ipc_gk7202v300_lpg-g5-wq", "gk7202v300", "000779su"),
        provider="it-blue",
        protocol_family="cloud-observed",
        notes=(
            "segunda Speed Dome IT-Blue observada em campo; neste ambiente está disponível somente via cloud",
            "não inferir URL RTSP/local sem evidência LAN do equipamento",
            "PIR, detecção de movimento/humano e alarme foram observados no aplicativo",
        ),
        validation="field-identified-cloud-only",
        confidence_floor=80,
        audio_mode="unknown",
        ptz_mode="unknown",
        features=("pir", "motion-detection", "human-detection", "alarm"),
    ),
    AkdbProfile(
        key="it-blue-camera",
        manufacturer="IT-Blue",
        canonical_type="camera",
        family="",
        device_types=("camera",),
        ports_any=(34567,),
        text_tokens=("it-blue", "it blue", "web viewer"),
        provider="it-blue",
        protocol_family="generic-onvif-rtsp",
        notes=("título Web Viewer + RTSP/34567 é evidência útil; validar fabricante antes de elevar confiança",),
        validation="field-detected",
        confidence_floor=50,
        audio_mode="bidirectional",
        audio_codecs=("unknown",),
        talkback_protocol="unvalidated",
        native_protocols=("rtsp-candidate", "onvif-candidate", "xm-dvrip-34567-candidate"),
    ),
)

AKDB_EXTENSION_REVISIONS = {"it-blue-x3-we2q": 9, "intelbras-imx-c": 4, "intelbras-mhdx": 3}


def _effective_profile(profile: AkdbProfile) -> AkdbProfile:
    """Read a newer official Sentinel extension without promoting field candidates.

    Packaged model signatures still identify the hardware; the shared AKDB can
    update its operational capabilities after an official bundle was applied.
    """
    core = record_by_legacy_key(profile.key)
    path = default_store_path()
    if core is None or not path.is_file():
        return profile
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)
        try:
            row = connection.execute(
                "SELECT revision,payload_json FROM domain_extensions WHERE stable_id=? AND domain='sentinel'",
                (core.stable_id,),
            ).fetchone()
        finally:
            connection.close()
        if not row or int(row[0]) <= AKDB_EXTENSION_REVISIONS.get(profile.key, 2):
            return profile
        payload = json.loads(row[1])
        if not isinstance(payload, dict):
            return profile
        changes = {}
        for field in ("max_analog_channels", "max_ip_channels", "max_total_channels", "stream_count"):
            if field in payload and type(payload[field]) is int and 0 <= payload[field] <= 64:
                changes[field] = payload[field]
        for field in ("video_codecs", "audio_codecs", "native_protocols", "onvif_profiles"):
            value = payload.get(field)
            if isinstance(value, list) and len(value) <= 32 and all(isinstance(v, str) and len(v) <= 80 for v in value):
                changes[field] = tuple(value)
        for field in ("audio_mode", "talkback_protocol", "talkback_scope", "talkback_validation"):
            value = payload.get(field)
            if isinstance(value, str) and len(value) <= 80:
                changes[field] = value
        return replace(profile, **changes) if changes else profile
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return profile



def reconcile_operational_profile_key(*, profile_key: str = "", provider: str = "", identity_text: str = "") -> str:
    """Upgrade only stale generic field identities when stronger operational evidence exists.

    This is intentionally narrow. 0.2.30 could leave early IT-Blue X3 field
    records pinned to the generic ``it-blue-camera`` profile, preventing the
    model-specific talkback capability from reaching the Live View even though
    PTZ already recognized the same SpeedDome/Ball identity.
    """
    current = str(profile_key or "")
    folded = str(identity_text or "").casefold()
    provider_folded = str(provider or "").casefold()
    # Early Intelbras detection attached the 1004 profile to generic NVD and
    # MHDX records solely because the vendor matched. Let explicit model
    # evidence replace that stale key without rewriting detection history.
    if current in {"", "intelbras-mhdx"} and (
        provider_folded == "intelbras" or "intelbras" in folded or "nvd" in folded or "mhdx" in folded
    ):
        for pattern, key in (
            (r"\bnvd[\s_-]*1416\b", "intelbras-nvd-1416"),
            (r"\bnvd[\s_-]*1516\b", "intelbras-nvd-1516"),
            (r"\bmhdx[\s_-]*1216\b", "intelbras-mhdx-1216"),
        ):
            if re.search(pattern, folded):
                return key
    if current in {"", "it-blue-camera"} and provider_folded == "it-blue":
        maker_ok = "it-blue" in folded or "it blue" in folded
        x3_hint = any(
            token in folded
            for token in ("x3-we2q", "xm535d1", "000a06cd", "speed dome", "speeddome", "ball")
        )
        if maker_ok and x3_hint:
            return "it-blue-x3-we2q"
    # Strong model evidence must win over stale recorder metadata left by older
    # field inventories. iMX C has required model tokens in AKDB, so this narrow
    # correction cannot turn an arbitrary Intelbras device into a Mibo camera.
    if any(token in folded for token in ("imx c", "imx-c", "imx_c")):
        intelbras_hint = (
            "intelbras" in folded or "mibo" in folded
            or provider_folded in {"intelbras", "intelbras-mibo"}
        )
        if intelbras_hint:
            return "intelbras-imx-c"
    return current

def match_profiles(*, text: str = "", ports: Iterable[int] = (), manufacturer: str = "") -> list[tuple[int, AkdbProfile]]:
    """Return AKDB matches sorted by conservative evidence score."""
    low = (text or "").lower()
    maker = (manufacturer or "").lower()
    portset = set(int(p) for p in ports)
    results: list[tuple[int, AkdbProfile]] = []
    for profile in PROFILES:
        if profile.required_tokens and not any(token.lower() in low for token in profile.required_tokens if token):
            continue
        score = 0
        if maker and profile.manufacturer.lower() == maker:
            score += 45
        token_hits = sum(1 for token in profile.text_tokens if token and token.lower() in low)
        score += min(50, token_hits * 25)
        if profile.ports_any and portset.intersection(profile.ports_any):
            score += 25
        if score:
            score = max(score, profile.confidence_floor)
            results.append((min(score, 100), _effective_profile(profile)))
    results.sort(key=lambda item: item[0], reverse=True)
    return results


def best_profile(*, text: str = "", ports: Iterable[int] = (), manufacturer: str = "") -> tuple[int, AkdbProfile] | None:
    matches = match_profiles(text=text, ports=ports, manufacturer=manufacturer)
    return matches[0] if matches else None


def _profile_for(*, provider: str = "", profile_key: str = "") -> AkdbProfile | None:
    if profile_key:
        profile = next((p for p in PROFILES if p.key == profile_key), None)
        if profile is not None:
            return _effective_profile(profile)
    if provider:
        matches = [p for p in PROFILES if p.provider == provider]
        if len(matches) == 1:
            return _effective_profile(matches[0])
        if matches:
            # Never project a model-specific feature onto the entire provider.
            generic = next((p for p in matches if not p.family), None)
            return _effective_profile(generic) if generic else None
    return None


def profile_by_provider(provider: str) -> AkdbProfile | None:
    return _profile_for(provider=provider)


def audio_capability(*, provider: str = "", profile_key: str = "") -> dict:
    profile = _profile_for(provider=provider, profile_key=profile_key)
    if profile is None:
        return {
            "mode": "unknown", "codecs": [], "talkback_protocol": "",
            "talkback_scope": "none", "talkback_validation": "unknown",
        }
    return {
        "mode": profile.audio_mode,
        "codecs": list(profile.audio_codecs),
        "talkback_protocol": profile.talkback_protocol,
        "talkback_scope": profile.talkback_scope,
        "talkback_validation": profile.talkback_validation,
    }


def ptz_capability(*, provider: str = "", profile_key: str = "") -> dict:
    """Return PTZ knowledge without turning recorder-mediated PTZ into ONVIF PTZ."""
    profile = _profile_for(provider=provider, profile_key=profile_key)
    if profile is None:
        return {"mode": "unknown", "scope": "none", "lens_count": 0, "features": [], "direct_control": False, "zoom": False}
    features = list(profile.features)
    mode = profile.ptz_mode
    direct_control = mode.startswith("onvif") or mode.startswith("dvrip")
    native = set(profile.native_protocols)
    backend = "dvrip" if ("xm-dvrip-34567" in native or mode.startswith("dvrip")) else ("onvif" if mode.startswith("onvif") else "")
    return {
        "mode": mode,
        "scope": str(profile.ptz_scope or "all"),
        "lens_count": int(profile.lens_count or 0),
        "features": features,
        "direct_control": direct_control,
        "backend": backend,
        "zoom": "zoom" in features and direct_control,
    }


def capability_map(*, provider: str = "", profile_key: str = "") -> dict:
    """Normalized, UI-safe capability map for one concrete AKDB profile.

    Unknown stays unknown: the function intentionally avoids optimistic feature
    inference from a provider name when multiple model profiles exist.
    """
    profile = _profile_for(provider=provider, profile_key=profile_key)
    if profile is None:
        return {
            "profile_key": "", "known": False, "canonical_type": "unknown", "device_types": [],
            "features": [], "native_protocols": [], "stream_count": 0, "video_codecs": [], "onvif_profiles": [],
            "audio": audio_capability(), "ptz": ptz_capability(),
            "max_analog_channels": 0, "max_ip_channels": 0, "max_total_channels": 0,
        }
    max_analog = int(profile.max_analog_channels or 0)
    max_ip = int(profile.max_ip_channels or 0)
    return {
        "profile_key": profile.key,
        "known": True,
        "manufacturer": profile.manufacturer,
        "family": profile.family,
        "canonical_type": profile.canonical_type,
        "device_types": list(profile.device_types),
        "validation": profile.validation,
        "protocol_family": profile.protocol_family,
        "features": list(profile.features),
        "native_protocols": list(profile.native_protocols),
        "stream_count": int(profile.stream_count or 0),
        "video_codecs": list(profile.video_codecs),
        "onvif_profiles": list(profile.onvif_profiles),
        "audio": audio_capability(profile_key=profile.key),
        "ptz": ptz_capability(profile_key=profile.key),
        "max_analog_channels": max_analog,
        "max_ip_channels": max_ip,
        "max_total_channels": int(profile.max_total_channels or (max_analog + max_ip)),
        "rtsp_main": profile.rtsp_main,
        "rtsp_sub": profile.rtsp_sub,
    }


def recorder_scan_limit(*, provider: str = "", profile_key: str = "", default: int = 32) -> int:
    caps = capability_map(provider=provider, profile_key=profile_key)
    total = int(caps.get("max_total_channels") or 0)
    return total if total > 0 else int(default)


def recorder_scan_capacity_for_device(*, provider: str = "", profile_key: str = "",
                                      model: str = "", name: str = "", saved_limit=None,
                                      saved_source: str = "") -> int:
    """Use model AKDB capacity, while retaining explicit per-device overrides."""
    try:
        manual = int(saved_limit)
    except (TypeError, ValueError):
        manual = 0
    saved_source = str(saved_source or "").lower()
    if saved_source == "manual" and 1 <= manual <= 64:
        return manual
    # Exact model text has precedence over a friendly name or a stale vendor
    # profile. Required model tokens in the AKDB prevent manufacturer-only
    # evidence from projecting the MHDX 1004 capacity onto other Intelbras DVRs.
    for identity in (str(model or ""), str(name or "")):
        match = best_profile(text=identity, manufacturer="Intelbras" if provider == "intelbras" else "")
        if match:
            profile = match[1]
            if profile.provider != provider or not profile.required_tokens:
                continue
            capacity = int(profile.max_total_channels or
                           (profile.max_analog_channels + profile.max_ip_channels))
            if capacity > 0:
                # The old dialog persisted a default of five without saying if
                # it was chosen manually. Repair that legacy cap for an NVD/1216.
                if (saved_source == "" and 1 <= manual <= 64
                        and not (manual == 5 and capacity == 16)):
                    return manual
                return min(64, capacity)
    if profile_key == "intelbras-mhdx":
        if saved_source == "" and 1 <= manual <= 64 and manual != 5:
            return manual
        return 16  # historical vendor-only match; model 1004 was not confirmed
    profile = profile_by_key(profile_key)
    if profile is not None and profile.provider == provider:
        capacity = int(profile.max_total_channels or
                       (profile.max_analog_channels + profile.max_ip_channels))
        if capacity > 0:
            if saved_source == "" and 1 <= manual <= 64 and not (manual == 5 and capacity == 16):
                return manual
            return min(64, capacity)
    if saved_source == "" and 1 <= manual <= 64:
        return manual
    return min(64, recorder_scan_limit(provider=provider, profile_key=profile_key,
                                       default=16 if provider == "intelbras" else 32))


def native_protocol_candidates(*, provider: str = "", profile_key: str = "") -> list[str]:
    """Names only; credentials/endpoints are resolved elsewhere and never stored in AKDB."""
    return list(capability_map(provider=provider, profile_key=profile_key).get("native_protocols") or [])


CANONICAL_TYPE_LABELS = {
    "camera": "Câmera IP",
    "camera-fixed": "Câmera IP fixa",
    "camera-ptz": "Speed Dome / PTZ",
    "camera-consumer": "Câmera IP / consumer",
    "camera-multilens": "Câmera multi-lente",
    "dvr": "DVR",
    "nvr": "NVR",
    "xvr": "XVR / Multi HD",
    "encoder": "Encoder",
    "decoder": "Decoder",
    "intercom": "Interfone / videoporteiro",
    "unknown": "Não identificado",
}


def canonical_type_label(value: str) -> str:
    value = str(value or "unknown").strip().lower()
    return CANONICAL_TYPE_LABELS.get(value, value or "Não identificado")


def profile_by_key(profile_key: str) -> AkdbProfile | None:
    profile = next((p for p in PROFILES if p.key == str(profile_key or "")), None)
    return _effective_profile(profile) if profile else None


def routing_kind_for_profile(profile_key: str) -> str:
    """Map an AKDB canonical type to the legacy operational routing kind.

    Canonical types are deliberately more specific than the old device.kind field.
    The router keeps the compatibility surface small while letting AKDB grow.
    """
    profile = profile_by_key(profile_key)
    if profile is None:
        return "unknown"
    canonical = profile.canonical_type
    if canonical.startswith("camera"):
        return "camera"
    if canonical in {"dvr", "nvr", "xvr"}:
        return canonical
    if len(profile.device_types) == 1 and profile.device_types[0] in {"camera", "dvr", "nvr", "xvr"}:
        return profile.device_types[0]
    return "unknown"


def _shared_core_record(profile: AkdbProfile):
    return record_by_legacy_key(profile.key)


def profile_by_stable_id(stable_id: str) -> AkdbProfile | None:
    target = str(stable_id or "")
    for profile in PROFILES:
        core = _shared_core_record(profile)
        if core is not None and core.stable_id == target:
            return profile
    return None


def validate_shared_core_alignment() -> list[str]:
    """Return divergence errors between Sentinel extensions and shared AKDB identity.

    The shared core owns manufacturer/type/stable identity. Sentinel may add CCTV
    capabilities, but it must not silently redefine the same device.
    """
    errors: list[str] = []
    for profile in PROFILES:
        core = _shared_core_record(profile)
        if core is None:
            errors.append(f"{profile.key}: missing shared AKDB core record")
            continue
        if core.manufacturer != profile.manufacturer:
            errors.append(f"{profile.key}: manufacturer differs ({profile.manufacturer} != {core.manufacturer})")
        if core.canonical_type != profile.canonical_type:
            errors.append(f"{profile.key}: canonical type differs ({profile.canonical_type} != {core.canonical_type})")
    return errors


def public_summary() -> list[dict]:
    """Serializable, credential-free AKDB information for UI/docs/tests.

    Identity/provenance comes from the shared Artin AKDB core; Sentinel-specific
    media/provider fields remain a domain extension.
    """
    rows: list[dict] = []
    for p in PROFILES:
        core = _shared_core_record(p)
        rows.append({
            "key": p.key,
            "stable_id": core.stable_id if core else "",
            "manufacturer": core.manufacturer if core else p.manufacturer,
            "family": p.family or (core.family if core else ""),
            "core_model": core.model if core else "",
            "core_variant": core.variant if core else "",
            "canonical_type": core.canonical_type if core else p.canonical_type,
            "subtype": core.subtype if core else "",
            "preferred_strategies": list(core.preferred_strategies) if core else [],
            "avoid_strategies": list(core.avoid_strategies) if core else [],
            "negative_knowledge": list(core.negative_knowledge) if core else [],
            "device_types": list(p.device_types),
            "provider": p.provider,
            "protocol_family": p.protocol_family,
            "validation": p.validation,
            "core_validation": core.validation_status if core else p.validation,
            "provenance": list(core.provenance) if core else [],
            "domains": list(core.domains) if core else ["sentinel"],
            "revision": int(core.revision) if core else 1,
            "ptz_mode": p.ptz_mode,
            "ptz_scope": p.ptz_scope,
            "lens_count": p.lens_count,
            "features": list(p.features),
            "notes": list(p.notes),
            "compatible_with": list(p.compatible_with),
            "audio_mode": p.audio_mode,
            "audio_codecs": list(p.audio_codecs),
            "talkback_protocol": p.talkback_protocol,
            "talkback_scope": p.talkback_scope,
            "talkback_validation": p.talkback_validation,
            "stream_count": p.stream_count,
            "video_codecs": list(p.video_codecs),
            "onvif_profiles": list(p.onvif_profiles),
            "native_protocols": list(p.native_protocols),
            "max_analog_channels": p.max_analog_channels,
            "max_ip_channels": p.max_ip_channels,
        })
    return rows
