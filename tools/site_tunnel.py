#!/usr/bin/env python3
"""Piloto de acesso ao DVR por encaminhamento SSH iniciado pelo Site.

Um servidor SSH intermediário precisa ser administrado pelo operador. Todos
os listeners remotos e locais ficam presos a 127.0.0.1; o DVR não recebe
conexões públicas nem mudança de configuração.
"""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import re
import subprocess


def host(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 253 or not re.fullmatch(r"[A-Za-z0-9.-]+", value):
        raise argparse.ArgumentTypeError("host inválido")
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        if re.fullmatch(r"[0-9.]+", value) or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in value.rstrip(".").split(".")
        ):
            raise argparse.ArgumentTypeError("host inválido") from None
    return value.rstrip(".").lower()


def ssh_user(value: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", value):
        raise argparse.ArgumentTypeError("usuário SSH inválido")
    return value


def port(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("porta inválida") from None
    if not 1024 <= result <= 65535:
        raise argparse.ArgumentTypeError("use uma porta entre 1024 e 65535")
    return result


def ssh_port(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("porta SSH inválida") from None
    if not 1 <= result <= 65535:
        raise argparse.ArgumentTypeError("porta SSH inválida")
    return result


def build_ssh_command(args: argparse.Namespace) -> list[str]:
    key = Path(args.identity).expanduser().resolve()
    if not key.is_file():
        raise ValueError(f"chave SSH não encontrada: {key}")
    ports = (args.relay_http, args.relay_rtsp, args.relay_service)
    if len(set(ports)) != 3:
        raise ValueError("as três portas do relay devem ser diferentes")
    base = [
        "ssh", "-F", "/dev/null", "-N", "-T", "-i", str(key),
        "-p", str(args.ssh_port), "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
    ]
    if args.known_hosts:
        known_hosts = Path(args.known_hosts).expanduser().resolve()
        if not known_hosts.is_file():
            raise ValueError(f"arquivo de host SSH confiável não encontrado: {known_hosts}")
        base += ["-o", f"UserKnownHostsFile={known_hosts}"]
    if args.role == "site":
        if args.dvr == "127.0.0.1" or args.dvr == "localhost":
            raise ValueError("o endereço do DVR deve ser acessível a partir do conector do Site")
        routes = ((args.relay_http, args.dvr, args.dvr_http_port),
                  (args.relay_rtsp, args.dvr, args.dvr_rtsp_port),
                  (args.relay_service, args.dvr, args.dvr_service_port))
        for listen, target, target_port in routes:
            base += ["-R", f"127.0.0.1:{listen}:{target}:{target_port}"]
    else:
        local_ports = (args.local_http, args.local_rtsp, args.local_service)
        if len(set(local_ports)) != 3:
            raise ValueError("as três portas locais devem ser diferentes")
        routes = zip(local_ports, ports)
        for listen, remote in routes:
            base += ["-L", f"127.0.0.1:{listen}:127.0.0.1:{remote}"]
    base.append(f"{args.ssh_user}@{args.relay}")
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Túnel SSH de Site para Artin Sentinel")
    roles = parser.add_subparsers(dest="role", required=True)
    for role in ("site", "operator"):
        sub = roles.add_parser(role)
        sub.add_argument("--relay", required=True, type=host, help="servidor SSH público controlado pelo operador")
        sub.add_argument("--ssh-user", required=True, type=ssh_user)
        sub.add_argument("--identity", required=True, help="caminho da chave SSH dedicada")
        sub.add_argument("--known-hosts", help="arquivo de chave pública do servidor SSH (fingerprint conferida)")
        sub.add_argument("--ssh-port", type=ssh_port, default=22)
        sub.add_argument("--relay-http", type=port, default=24080)
        sub.add_argument("--relay-rtsp", type=port, default=24554)
        sub.add_argument("--relay-service", type=port, default=27777)
        sub.add_argument("--dry-run", action="store_true", help="validar parâmetros sem conectar")
    roles.choices["site"].add_argument("--dvr", type=host, required=True, help="IP do DVR na rede do Site")
    roles.choices["site"].add_argument("--dvr-http-port", type=ssh_port, default=80)
    roles.choices["site"].add_argument("--dvr-rtsp-port", type=ssh_port, default=554)
    roles.choices["site"].add_argument("--dvr-service-port", type=ssh_port, default=37777)
    roles.choices["operator"].add_argument("--local-http", type=port, default=18080)
    roles.choices["operator"].add_argument("--local-rtsp", type=port, default=18554)
    roles.choices["operator"].add_argument("--local-service", type=port, default=37777)
    args = parser.parse_args()
    try:
        command = build_ssh_command(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(("Site → relay" if args.role == "site" else "Sentinel → relay")
          + " • SSH autenticado • portas limitadas a 127.0.0.1", flush=True)
    if args.dry_run:
        print("Parâmetros válidos; nenhuma conexão foi iniciada.")
        return 0
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        parser.error("o cliente OpenSSH (ssh) não está instalado")


if __name__ == "__main__":
    raise SystemExit(main())
