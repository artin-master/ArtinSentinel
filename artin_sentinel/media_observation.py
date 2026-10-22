"""Metadata from the decoder's actual input, never from an assumed brand."""
import re

def observe_video(line):
    match=re.search(r'Video:\s*([\w]+).*?\b(\d{2,5})x(\d{2,5})\b',line)
    if not match:return None
    codec={'h264':'H.264','hevc':'H.265','mpeg4':'MPEG-4','mjpeg':'MJPEG'}.get(match[1],match[1].upper())
    fps=re.search(r'([\d.]+) fps',line)
    return dict(codec=codec,width=int(match[2]),height=int(match[3]),fps=float(fps[1]) if fps else 0.0)

def transport_name(url):
    from urllib.parse import urlsplit
    scheme=urlsplit(url).scheme
    return {'hik-sdk':'Hikvision SDK local','intelbras-cloud':'Intelbras Cloud','intelbras-wine':'Intelbras Cloud / Wine','dvrip':'DVRIP'}.get(scheme,'RTSP / FFmpeg')

def session_label(session):
    info=getattr(session,'media_info',None) or {}
    media=(f"{info['codec']} · {info['width']}×{info['height']}" if info else 'Identificando vídeo…')
    return media+' · '+transport_name(session.url)
