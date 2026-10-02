"""Read-only diagnosis of saved Main/Sub routes, with no URL in the result."""
from dataclasses import dataclass
from threading import Event

from .live import MediaProbeResult, ffmpeg_decoders, local_decoder_available, probe_rtsp_media_capabilities


@dataclass(frozen=True, slots=True)
class StreamDiagnostic:
    channel_no: int
    stream: str
    state: str
    media: MediaProbeResult
    video_decoder: bool | None = None
    audio_decoder: bool | None = None

    def summary(self) -> str:
        video = self.media.video_codec or ("codec não identificado" if self.media.video_present else "não confirmado")
        audio_present = self.media.audio_present
        if audio_present is None and self.media.ok:
            audio_present = self.media.has_audio
        audio = self.media.audio_codec or ("codec não identificado" if audio_present else "ausente" if audio_present is False else "não verificado")
        parts = [f"Vídeo: {video}", f"Áudio: {audio}"]
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
        if self.media.error_code:
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
            if url not in cache:
                cache[url] = probe_rtsp_media_capabilities(url, username, password, timeout=timeout)
            media = cache[url]
            video_decoder = local_decoder_available(media.video_codec) if decoders and media.video_codec else None
            audio_decoder = local_decoder_available(media.audio_codec) if decoders and media.audio_codec else None
            if media.error_code:
                state = media.error_code
            elif video_decoder is False:
                state = "codec_unsupported"
            elif media.video_codec or media.video_present:
                state = "video_without_audio" if media.audio_present is False or (media.ok and not media.has_audio and media.audio_present is None) else "ok"
                if audio_decoder is False:
                    state = "audio_codec_unsupported"
            else:
                state = "no_video" if media.ok else "media_unverified"
            output.append(StreamDiagnostic(int(channel["channel_no"]), label, state, media, video_decoder, audio_decoder))
            if progress:
                progress(f"Canal {channel['channel_no']} • {label} verificado")
    return output


STATE_LABELS = {
    "ok": "Vídeo/áudio identificado", "video_without_audio": "Vídeo sem áudio",
    "authentication": "Autenticação", "stream_not_found": "Stream não encontrado",
    "timeout": "Timeout", "rtsp_unavailable": "RTSP indisponível",
    "codec_unsupported": "Codec de vídeo não suportado", "audio_codec_unsupported": "Codec de áudio não suportado",
    "probe_unavailable": "ffprobe indisponível", "invalid_response": "Resposta inválida",
    "other_error": "Não confirmado", "no_video": "Sem faixa de vídeo", "media_unverified": "Mídia inconclusiva",
}
