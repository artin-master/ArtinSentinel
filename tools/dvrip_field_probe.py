#!/usr/bin/env python3
"""Run one isolated DVRIP media attempt for an operator-selected channel."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artin_sentinel.dvrip_field_probe import probe_dvrip_single_shot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="IP/host LAN da câmera IT-Blue")
    parser.add_argument("--channel", required=True, type=int, choices=(0, 1, 2))
    parser.add_argument("--subtype", required=True, type=int, choices=(0, 1), help="0=Main; 1=Sub/Extra1")
    parser.add_argument("--timeout", type=float, default=8.0, help="Limite da leitura de mídia, 0.1–30 s")
    args = parser.parse_args()

    lock_fd = os.open("/tmp/artin-sentinel-dvrip-field-probe.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Outra sonda DVRIP está em execução; aguarde o fechamento antes de tentar novamente.", file=sys.stderr)
            return 2

        username = getpass.getpass("Usuário DVRIP (entrada oculta): ")
        password = getpass.getpass("Senha DVRIP (entrada oculta): ")
        try:
            result = probe_dvrip_single_shot(
                args.host, username, password,
                channel=args.channel, subtype=args.subtype, timeout=args.timeout,
            )
        except Exception as exc:
            # Never expose arbitrary exception text that could contain endpoint
            # or protocol details; report only its class for field diagnostics.
            print(f"Sonda encerrada com erro sanitizado: {type(exc).__name__}", file=sys.stderr)
            return 1
        print(json.dumps({
            "channel": result.channel,
            "subtype": result.subtype,
            "order_ms": [{"stage": event.stage, "elapsed_ms": event.elapsed_ms} for event in result.events],
            "login_ret": result.login_ret,
            "claim_ret": result.claim_ret,
            "start_sent": result.start_sent,
            "packets_received": result.packets_received,
            "bytes_received": result.bytes_received,
            "first_video_packet": result.first_video_packet,
            "codec": result.codec,
            "duration_ms": result.duration_ms,
            "error_code": result.error_code,
            "socket_closed": result.socket_closed,
        }, ensure_ascii=False, indent=2))
        return 0 if result.first_video_packet else 1
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
