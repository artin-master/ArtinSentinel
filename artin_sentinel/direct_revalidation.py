"""Conservative direct-camera inventory and sanitized per-position evidence."""
from dataclasses import dataclass
import re
from urllib.parse import urlparse, parse_qs


@dataclass(frozen=True)
class DirectChannelRetirement:
    channel: int
    equivalent_channel: int
    evidence: str = 'operator_confirmed_visual_alias'


def previously_confirmed(row):
    row = dict(row)
    return bool(row.get('route_kind') == 'direct' and row.get('rtsp_url') and (
        row.get('available') or str(row.get('detail') or '').startswith('Rota direta •')
    ))


def scan_diagnostic(number, route, profile, ok, detail, username, password, *,
                    decision='candidate', previous='new', codec='', native_index=None):
    from .talkback import sanitize_talkback_diagnostic
    text = sanitize_talkback_diagnostic(str(detail or ''), username, password)
    lowered = text.casefold()
    error = '' if ok else ('timeout' if 'timeout' in lowered or 'limite de tempo' in lowered else
                          'authentication' if '401' in lowered or 'credencial' in lowered else
                          'not_found' if '404' in lowered or 'não existe' in lowered else 'unconfirmed')
    size = re.search(r'\b(\d{2,5})x(\d{2,5})\b', text)
    if not codec:
        match = re.search(r'\b(hevc|h26[45]|mjpeg)\b', lowered)
        codec = match.group(1) if match else ''
    parsed = urlparse(route)
    if native_index is None:
        query = parse_qs(parsed.query)
        values = query.get('channel')
        match = re.search(r'(?:_|&)channel=(\d+)(?:_|&)', parsed.path)
        native_index = int(values[0]) if values and values[0].isdigit() else int(match.group(1)) if match else None
    return dict(position=number, native_index=native_index,
                route=re.sub(r'([a-z]+://)[^/@\s]+@', r'\1<oculto>@', sanitize_talkback_diagnostic(route, username, password)), profile=profile,
                probe='DVRIP media' if parsed.scheme == 'dvrip' else 'ffprobe/RTSP',
                result='confirmed' if ok else 'unconfirmed', codec=codec,
                resolution=size.group(0) if size else 'not_reported', error=error,
                detail=text, decision=decision, previous_state=previous)


def diagnostic_line(item):
    return (f"Posição {item['position']} • índice {item['native_index']} • {item['profile']} • "
            f"{item['route']} • {item['probe']}: {item['result']} • "
            f"{item['codec'] or '?'} {item['resolution']} • erro={item['error'] or '—'} • "
            f"anterior={item['previous_state']} • decisão={item['decision']} • {item['detail']}")
