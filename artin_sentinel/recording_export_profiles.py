"""Export-only profiles. Never alter playback, the DVR, or its stored recordings."""

COMPACT_VIDEO_KBPS = 900
COMPACT_AUDIO_KBPS = 48


def validate_quality(quality):
    if quality not in {'original', 'compact'}:
        raise ValueError('Qualidade de exportação inválida; escolha Original ou Compacto')
    return quality


def video_args(quality='original'):
    validate_quality(quality)
    if quality == 'original':
        return ['-c:v', 'copy']
    return ['-vf', "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,"
                   "fps=fps='if(gt(source_fps,0),min(source_fps,15),15)'",
            '-c:v', 'libx264', '-preset', 'veryfast', '-threads', '2',
            '-b:v', '900k', '-maxrate', '1200k', '-bufsize', '1800k', '-pix_fmt', 'yuv420p']


def audio_args(quality='original', include_audio=True):
    validate_quality(quality)
    if not include_audio:
        return ['-an']
    return ['-map', '0:a:0?', '-c:a', 'aac', *(['-b:a', '48k', '-ac', '1'] if quality == 'compact' else [])]


def export_note(quality, duration_seconds, include_audio):
    validate_quality(quality)
    if quality == 'original':
        return 'Original • vídeo sem recodificação'
    size = max(0, duration_seconds)*(COMPACT_VIDEO_KBPS+(COMPACT_AUDIO_KBPS if include_audio else 0))*1000/8/1_000_000*1.02
    return f'Compacto • estimativa ≈ {size:.1f} MB • tamanho pode variar'
