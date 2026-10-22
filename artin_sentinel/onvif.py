from __future__ import annotations
import re
import socket
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

MULTICAST = ("239.255.255.250", 3702)

PROBE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
 <e:Header>
  <w:MessageID>uuid:{message_id}</w:MessageID>
  <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
  <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
 </e:Header>
 <e:Body>
  <d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>
 </e:Body>
</e:Envelope>"""

@dataclass(slots=True)
class OnvifDiscoveryResult:
    ip: str
    xaddrs: list[str]
    scopes: list[str]
    endpoint: str = ""

def _first_text(xml: str, tag: str) -> str:
    match = re.search(
        rf"<(?:\w+:)?{tag}[^>]*>(.*?)</(?:\w+:)?{tag}>",
        xml, re.I | re.S
    )
    return match.group(1).strip() if match else ""

def discover(timeout: float = 2.5) -> list[OnvifDiscoveryResult]:
    message = PROBE_TEMPLATE.format(message_id=uuid.uuid4())
    found: dict[str, OnvifDiscoveryResult] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        sock.sendto(message.encode("utf-8"), MULTICAST)

        while True:
            try:
                data, address = sock.recvfrom(65535)
            except socket.timeout:
                break

            xml = data.decode("utf-8", "replace")
            xaddrs = _first_text(xml, "XAddrs").split()
            scopes = _first_text(xml, "Scopes").split()
            endpoint = _first_text(xml, "Address")
            ip = address[0]

            for url in xaddrs:
                try:
                    parsed = urlparse(url)
                    if parsed.hostname:
                        ip = parsed.hostname
                except Exception:
                    pass

            key = endpoint or ip
            found[key] = OnvifDiscoveryResult(
                ip=ip, xaddrs=xaddrs, scopes=scopes, endpoint=endpoint
            )
    finally:
        sock.close()

    return list(found.values())
