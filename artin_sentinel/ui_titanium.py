"""Titanium + Cyan visual identity for Artin Sentinel.

Vector-only assets keep the approved visual consistent on Linux and Windows
without scaling a raster spritesheet. Icons are intentionally small and clear
at 20–24 px, matching the approved control panel.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_SHELL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<defs>
 <linearGradient id="m" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff"/><stop offset=".38" stop-color="#cbd8e2"/>
  <stop offset=".75" stop-color="#748a9a"/><stop offset="1" stop-color="#eef5f8"/>
 </linearGradient>
 <filter id="g" x="-40%" y="-40%" width="180%" height="180%">
  <feGaussianBlur stdDeviation=".35" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
 </filter>
</defs>
<g fill="none" stroke="url(#m)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
{body}
</g>
</svg>"""

_CYAN = "#30d8ff"
_RED = "#ff4057"

_BODIES = {
    "camera": f"""<path d="M3 9l12-3 2 7-12 3z"/><path d="M6 16v3M4 19h5"/>
      <circle cx="18.3" cy="12.3" r="2.1" stroke="{_CYAN}"/><path d="M20 11l2-1v4l-2-1" stroke="{_CYAN}"/>""",
    "recorder": f"""<rect x="3" y="6.5" width="18" height="11" rx="2"/><path d="M6 10h8M6 13h8"/>
      <circle cx="18" cy="12" r="1.3" fill="{_CYAN}" stroke="{_CYAN}"/>""",
    "live": f"""<rect x="3" y="3" width="7.5" height="7.5"/><rect x="13.5" y="3" width="7.5" height="7.5" stroke="{_CYAN}"/>
      <rect x="3" y="13.5" width="7.5" height="7.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5"/>""",
    "play": f"""<path d="M7 4l12 8-12 8z" stroke="{_CYAN}" filter="url(#g)"/>""",
    "pause": f"""<path d="M8 5v14M16 5v14" stroke="{_CYAN}" filter="url(#g)"/>""",
    "stop": """<rect x="6" y="6" width="12" height="12" rx="1"/>""",
    "record": f"""<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="4.3" fill="{_RED}" stroke="{_RED}"/>""",
    "timeline": f"""<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 9h16"/>
      <rect x="8" y="12" width="3" height="3" fill="{_CYAN}" stroke="{_CYAN}"/><rect x="13" y="12" width="3" height="3" stroke="{_CYAN}"/>""",
    "export": f"""<path d="M12 3v12M8 11l4 4 4-4" stroke="{_CYAN}" filter="url(#g)"/>
      <path d="M5 16v4h14v-4"/>""",
    "microphone": f"""<rect x="9" y="3" width="6" height="12" rx="3" stroke="{_CYAN}"/>
      <path d="M6.5 11.5a5.5 5.5 0 0011 0M12 17v4M9 21h6"/>""",
    "audio": f"""<path d="M4 10h4l5-4v12l-5-4H4z"/><path d="M16 9a4 4 0 010 6M18.5 6.5a8 8 0 010 11" stroke="{_CYAN}"/>""",
    "ptz": f"""<circle cx="12" cy="12" r="3" stroke="{_CYAN}"/><path d="M12 3l-2 3h4zM12 21l-2-3h4zM3 12l3-2v4zM21 12l-3-2v4z"/>""",
    "diagnose": f"""<path d="M3 13h4l2-6 3 11 3-8 2 3h4" stroke="{_CYAN}" filter="url(#g)"/>""",
    "settings": f"""<circle cx="12" cy="12" r="3" stroke="{_CYAN}"/>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>""",
    "add": f"""<path d="M12 4v16M4 12h16" stroke="{_CYAN}" filter="url(#g)"/>""",
    "edit": f"""<path d="M5 19l3.5-.8L19 7.7 16.3 5 5.8 15.5z"/><path d="M14.8 6.5l2.7 2.7" stroke="{_CYAN}"/>""",
    "channels": f"""<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6" stroke="{_CYAN}"/>
      <rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>""",
    "more": """<circle cx="5" cy="12" r="1.4" fill="#dce7f0"/><circle cx="12" cy="12" r="1.4" fill="#dce7f0"/><circle cx="19" cy="12" r="1.4" fill="#dce7f0"/>""",
    "search": f"""<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5" stroke="{_CYAN}" filter="url(#g)"/>""",
    "link": f"""<path d="M9.5 14.5l-1.7 1.7a4 4 0 01-5.6-5.6l3-3a4 4 0 015.6 0" stroke="{_CYAN}"/>
      <path d="M14.5 9.5l1.7-1.7a4 4 0 015.6 5.6l-3 3a4 4 0 01-5.6 0"/><path d="M8.5 15.5l7-7"/>""",
    "delete": f"""<path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13M10 10v7M14 10v7" stroke="{_RED}"/>""",
}

_MARK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<defs>
 <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#f8fbfd"/><stop offset=".22" stop-color="#a9bac7"/>
  <stop offset=".52" stop-color="#edf4f8"/><stop offset=".78" stop-color="#718797"/>
  <stop offset="1" stop-color="#dce8ef"/>
 </linearGradient>
 <filter id="glow"><feGaussianBlur stdDeviation="1.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<path d="M25 24L48 12h32l23 12-7 16-15-8H47l-15 8z" fill="none" stroke="url(#metal)" stroke-width="9" stroke-linejoin="round"/>
<path d="M31 39l22 13h22l22-13v34c0 16-14 30-33 42-19-12-33-26-33-42z" fill="#071522" stroke="url(#metal)" stroke-width="9" stroke-linejoin="round"/>
<path d="M43 63l15 4 6 10-10 12-13-11zM85 63l-15 4-6 10 10 12 13-11z" fill="#d7e5ee" stroke="{_CYAN}" stroke-width="2.8" filter="url(#glow)"/>
<circle cx="54" cy="74" r="3.4" fill="{_CYAN}" filter="url(#glow)"/><circle cx="74" cy="74" r="3.4" fill="{_CYAN}" filter="url(#glow)"/>
<path d="M64 79l6 8-6 11-6-11z" fill="url(#metal)" stroke="{_CYAN}" stroke-width="2"/>
</svg>"""


def _render(svg: str, size: int) -> QPixmap:
    pixmap=QPixmap(size,size)
    pixmap.fill(Qt.transparent)
    renderer=QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing,True)
    renderer.render(painter)
    painter.end()
    return pixmap


@lru_cache(maxsize=128)
def titanium_icon(name: str, size: int = 24) -> QIcon:
    body=_BODIES.get(name,_BODIES["diagnose"])
    return QIcon(_render(_SHELL.format(body=body),int(size)))


@lru_cache(maxsize=16)
def titanium_mark(size: int = 64) -> QPixmap:
    return _render(_MARK,int(size))


def titanium_app_icon(size: int = 128) -> QIcon:
    return QIcon(titanium_mark(size))
