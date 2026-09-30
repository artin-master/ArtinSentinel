from __future__ import annotations
import re
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

@dataclass(slots=True)
class ProbeResult:
    ok: bool
    detail: str = ""
    latency_ms: float | None = None

def tcp_probe(host: str, port: int, timeout: float = 1.5) -> ProbeResult:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return ProbeResult(True, f"TCP {port} acessível", (time.perf_counter() - start) * 1000)
    except OSError as exc:
        return ProbeResult(False, f"TCP {port}: {exc}")

def ping_probe(host: str, timeout_s: int = 1) -> ProbeResult:
    start = time.perf_counter()
    try:
        cp = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), host],
            capture_output=True, text=True, timeout=timeout_s + 1
        )
        ok = cp.returncode == 0
        match = re.search(r"time[=<]([0-9.]+)\s*ms", cp.stdout)
        latency = float(match.group(1)) if match else ((time.perf_counter() - start) * 1000 if ok else None)
        return ProbeResult(ok, "ICMP OK" if ok else "Sem resposta ICMP", latency)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ProbeResult(False, "ping indisponível/timeout")

def http_probe(url: str, timeout: float = 2.5) -> ProbeResult:
    start = time.perf_counter()
    try:
        context = ssl.create_default_context()
        req = Request(url, method="HEAD", headers={"User-Agent": "Artin-Sentinel/0.1"})
        try:
            response = urlopen(req, timeout=timeout, context=context)
        except Exception:
            req = Request(url, method="GET", headers={"User-Agent": "Artin-Sentinel/0.1"})
            response = urlopen(req, timeout=timeout, context=context)
        code = getattr(response, "status", 200)
        response.close()
        return ProbeResult(True, f"HTTP {code}", (time.perf_counter() - start) * 1000)
    except Exception as exc:
        return ProbeResult(False, f"HTTP: {type(exc).__name__}")

def rtsp_options(url: str, timeout: float = 2.5) -> ProbeResult:
    parsed = urlparse(url if "://" in url else "rtsp://" + url)
    host = parsed.hostname or ""
    port = parsed.port or 554
    if not host:
        return ProbeResult(False, "URL RTSP inválida")

    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            target = url if "://" in url else "rtsp://" + url
            request = (
                f"OPTIONS {target} RTSP/1.0\r\n"
                "CSeq: 1\r\n"
                "User-Agent: Artin-Sentinel/0.1\r\n\r\n"
            ).encode()
            sock.sendall(request)
            data = sock.recv(1024).decode("latin1", "replace")
        first = data.splitlines()[0] if data else ""
        ok = first.startswith("RTSP/")
        return ProbeResult(
            ok,
            first or "Sem resposta RTSP",
            (time.perf_counter() - start) * 1000 if ok else None
        )
    except OSError as exc:
        return ProbeResult(False, f"RTSP: {exc}")
