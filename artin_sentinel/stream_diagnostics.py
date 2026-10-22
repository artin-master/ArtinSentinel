"""Read-only diagnosis of saved Main/Sub routes, with no URL in the result."""
from dataclasses import dataclass
from threading import Event
from urllib.parse import urlparse
from .xm_dvrip import parse_dvrip_route, probe_dvrip_media

from .live import MediaProbeResult, ffmpeg_decoders, local_decoder_available, probe_rtsp_media_capabilities


@dataclass(frozen=True, slots=True)
class StreamDiagnostic:
    channel_no: int
    stream: str
    state: str
    media: MediaProbeResult
    video_decoder: bool | None = None
    audio_decoder: bool | None = None
    protocol: str = "RTSP"
    native_index: int | None = None
    subtype: int | None = None

    def summary(self) -> str:
        video = self.media.video_codec or ("codec não identificado" if self.media.video_present else "não confirmado")
        audio_present = self.media.audio_present
        if audio_present is None and self.media.ok and self.protocol != "DVRIP nativo":
            audio_present = self.media.has_audio
        audio = self.media.audio_codec or ("codec não identificado" if audio_present else "ausente" if audio_present is False else "não verificado")
        parts = [f"Protocolo: {self.protocol}", f"Vídeo: {video}", f"Áudio: {audio}"]
        if self.native_index is not None:
            parts.extend([f"Índice DVRIP: {self.native_index}", f"Subtype: {self.subtype}"])
        if self.media.video_width and self.media.video_height:
            parts.append(f"{self.media.video_width}x{self.media.video_height}")
        if self.media.audio_sample_rate:
            parts.append(f"{self.media.audio_sample_rate} Hz")
        if self.media.audio_channels:
            parts.append(f"{self.media.audio_channels} canal(is) de áudio")
        if self.video_decoder is False:
            parts.append("decoder de vídeo local indisponível")
        if self.audio_decoder is False:
            parts.append("decoder de áudio local indisponível")
        if self.media.error_code or self.protocol == "DVRIP nativo":
            parts.append(self.media.detail)
        return " • ".join(parts)


def diagnose_saved_streams(channels, username="", password="", *, timeout=6.0,
                           cancel_event: Event | None = None, progress=None) -> list[StreamDiagnostic]:
    """Inspect only saved routes; do not discover paths or change availability."""
    output = []
    cache = {}
    decoders = ffmpeg_decoders()
    for channel in channels:
        for label, url in (("Main", channel.get("main_rtsp_url") or channel.get("rtsp_url") or ""),
                           ("Sub", channel.get("sub_rtsp_url") or "")):
            if cancel_event is not None and cancel_event.is_set():
                return output
            native = urlparse(url).scheme.lower() == "dvrip"
            target = None
            if url not in cache:
                if native:
                    try:
                        target = parse_dvrip_route(url)
                    except (ValueError, TypeError):
                        cache[url] = MediaProbeResult(detail="Rota DVRIP inválida", error_code="invalid_response")
                    else:
                        host, port, index, subtype = target
                        probe = probe_dvrip_media(host, username, password, port=port, channel=index,
                                                 subtype=subtype, timeout=timeout, cancel_event=cancel_event)
                        cache[url] = MediaProbeResult(ok=probe.ok, video_codec=probe.codec,
                            video_present=True if probe.ok else None, audio_present=None,
                            detail=probe.detail, error_code=probe.error_code or ("" if probe.ok else "media_unverified"))
                else:
                    cache[url] = probe_rtsp_media_capabilities(url, username, password, timeout=timeout)
            if cancel_event is not None and cancel_event.is_set():
                return output
            if native and target is None:
                try:
                    target = parse_dvrip_route(url)
                except (ValueError, TypeError):
                    pass
            media = cache[url]
            video_decoder = local_decoder_available(media.video_codec) if decoders and media.video_codec else None
            audio_decoder = local_decoder_available(media.audio_codec) if decoders and media.audio_codec else None
            if media.error_code:
                state = media.error_code
            elif video_decoder is False:
                state = "codec_unsupported"
            elif media.video_codec or media.video_present:
                state = "video_without_audio" if media.audio_present is False or (not native and media.ok and not media.has_audio and media.audio_present is None) else "ok"
                if audio_decoder is False:
                    state = "audio_codec_unsupported"
            else:
                state = "no_video" if media.ok else "media_unverified"
            if native and state == "ok":
                state = "native_validated"
            output.append(StreamDiagnostic(int(channel["channel_no"]), label, state, media, video_decoder, audio_decoder,
                "DVRIP nativo" if native else "RTSP", target[2] if target else None, target[3] if target else None))
            if progress:
                progress(f"Canal {channel['channel_no']} • {label} verificado")
    return output


STATE_LABELS = {
    "native_validated": "Validado (DVRIP)",
    "protocol_unsupported": "DVRIP não suportado",
    "ok": "Vídeo/áudio identificado", "video_without_audio": "Vídeo sem áudio",
    "authentication": "Autenticação", "stream_not_found": "Stream não encontrado",
    "timeout": "Timeout", "rtsp_unavailable": "RTSP indisponível",
    "codec_unsupported": "Codec de vídeo não suportado", "audio_codec_unsupported": "Codec de áudio não suportado",
    "probe_unavailable": "ffprobe indisponível", "invalid_response": "Resposta inválida",
    "other_error": "Não confirmado", "no_video": "Sem faixa de vídeo", "media_unverified": "Mídia inconclusiva",
}
