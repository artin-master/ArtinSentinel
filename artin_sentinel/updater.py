from __future__ import annotations

"""Artin Sentinel online update service.

The updater is deliberately split into four stages:

1. read a small ArtinUpdates manifest over HTTPS;
2. download a versioned ZIP only after explicit user consent;
3. verify SHA-256 (and Ed25519 when a trusted key is configured) before
   extracting anything executable;
4. hand the verified package to an external helper.  The helper waits for the
   Sentinel process to close, runs ``install.sh`` and lets the existing
   post-update flow relaunch the application and show release notes.

No update is installed silently.  User databases, layouts, AKDB data and
keyring secrets live outside the package tree and are not touched by the
installer.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from .private_update_auth import load_token, token_for_download


APP_ID = "artin-sentinel"
MANIFEST_SCHEMA = "artin-update-manifest-v1"


class _NoPrivateRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirecionamento de atualização privada bloqueado para proteger a chave")


def _open_update_request(req: Request, *, timeout: float, auth_token: str | None):
    return build_opener(_NoPrivateRedirect).open(req, timeout=timeout) if auth_token else urlopen(req, timeout=timeout)
DEFAULT_CHANNEL = "stable"
OFFICIAL_MANIFEST_BASE_URL = "https://raw.githubusercontent.com/artin-master/ArtinUpdates/main"
DEFAULT_MANIFEST_BASE_URL = os.environ.get("ARTIN_UPDATES_BASE_URL", "").strip() or OFFICIAL_MANIFEST_BASE_URL
UPDATE_USER_AGENT = "Artin-Sentinel-Updater/0.2.30"
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
STARTUP_CHECK_INTERVAL_HOURS = 6


def other_sentinel_pids(current_pid: int, runtime_dir: Path | None = None) -> list[int]:
    """Find other live instances of this user's installed Sentinel."""
    runtime = Path(runtime_dir) if runtime_dir else Path.home() / ".local/share/artin-sentinel/runtime"
    targets = {str(runtime / "bin/artin-sentinel"), str(Path.home() / ".local/bin/artin-sentinel")}
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) in {os.getpid(), int(current_pid)}:
            continue
        try:
            if entry.stat().st_uid != os.getuid() or (entry / "stat").read_text().split(") ", 1)[1][0] == "Z":
                continue
            args = [os.fsdecode(part) for part in (entry / "cmdline").read_bytes().split(b"\0") if part]
        except (OSError, PermissionError, IndexError):
            continue
        if any(arg in targets for arg in args) or any(
            args[i:i + 2] == ["-m", "artin_sentinel.app"] for i in range(len(args) - 1)
        ):
            matches.append(int(entry.name))
    return sorted(matches)


@dataclass(slots=True)
class ReleaseInfo:
    """Compatibility structure kept for the older GitHub Release foundation."""

    tag: str
    version: str
    name: str
    body: str
    html_url: str
    zip_url: str = ""
    sha256_url: str = ""


@dataclass(slots=True)
class UpdateManifest:
    schema: str
    app_id: str
    channel: str
    version: str
    title: str
    notes: list[str]
    package_url: str
    sha256: str
    release_url: str = ""
    published_at: str = ""
    package_size: int = 0
    minimum_python: str = "3.12"
    mandatory: bool = False
    signature_key_id: str = ""
    signature_value: str = ""
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class UpdateSettings:
    manifest_base_url: str = DEFAULT_MANIFEST_BASE_URL
    channel: str = DEFAULT_CHANNEL
    check_on_startup: bool = True
    require_signature: bool = False
    last_checked_at: str = ""
    last_seen_version: str = ""


@dataclass(slots=True)
class StagedUpdate:
    version: str
    title: str
    stage_dir: str
    package_path: str
    install_root: str
    helper_path: str
    log_path: str
    signature_verified: bool = False


def normalize_version(text: str) -> tuple[int, ...]:
    value = (text or "").strip().lower().lstrip("v")
    parts: list[int] = []
    for token in value.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def is_newer(candidate: str, current: str) -> bool:
    a = normalize_version(candidate)
    b = normalize_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def latest_github_release(repo: str, timeout: float = 5.0) -> ReleaseInfo:
    """Backward-compatible metadata reader from the 0.2.2 foundation."""

    repo = (repo or "").strip().strip("/")
    if repo.startswith("https://github.com/"):
        repo = repo[len("https://github.com/") :].strip("/")
    if repo.count("/") != 1:
        raise ValueError("Repositório GitHub deve estar no formato owner/repo")
    req = Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": UPDATE_USER_AGENT},
    )
    with _open_update_request(req, timeout=timeout, auth_token=auth_token) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name") or "")
    assets = payload.get("assets") or []
    zip_url = ""
    sha_url = ""
    for asset in assets:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.lower().endswith(".zip") and not zip_url:
            zip_url = url
        if "sha256" in name.lower() and not sha_url:
            sha_url = url
    return ReleaseInfo(
        tag=tag,
        version=tag.lstrip("vV"),
        name=str(payload.get("name") or tag),
        body=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url") or ""),
        zip_url=zip_url,
        sha256_url=sha_url,
    )


def settings_path(data_directory: Path) -> Path:
    return Path(data_directory) / "update-settings.json"


def trusted_keys_path(data_directory: Path) -> Path:
    return Path(data_directory) / "trusted-update-keys.json"


def load_update_settings(data_directory: Path) -> UpdateSettings:
    path = settings_path(data_directory)
    defaults = UpdateSettings()
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    channel = str(payload.get("channel") or defaults.channel).lower()
    if channel not in {"stable", "beta"}:
        channel = "stable"
    return UpdateSettings(
        manifest_base_url=str(payload.get("manifest_base_url") or defaults.manifest_base_url).strip(),
        channel=channel,
        check_on_startup=bool(payload.get("check_on_startup", defaults.check_on_startup)),
        require_signature=bool(payload.get("require_signature", defaults.require_signature)),
        last_checked_at=str(payload.get("last_checked_at") or ""),
        last_seen_version=str(payload.get("last_seen_version") or ""),
    )


def save_update_settings(data_directory: Path, settings: UpdateSettings) -> None:
    path = settings_path(data_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def resolve_manifest_url(base_url: str, channel: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        raise ValueError("Fonte de atualizações ArtinUpdates ainda não configurada")
    channel = (channel or "stable").lower()
    if channel not in {"stable", "beta"}:
        raise ValueError("Canal de atualização inválido")
    if base_url.lower().endswith(".json"):
        return base_url
    return base_url.rstrip("/") + f"/sentinel/{channel}.json"


def _read_url(url: str, timeout: float = 8.0, max_bytes: int = 2 * 1024 * 1024, *, auth_token: str | None = None) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http", "file"}:
        raise ValueError("A fonte de atualização deve usar HTTPS")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("A fonte oficial de atualização deve usar HTTPS")
    headers = {"Accept": "application/json", "User-Agent": UPDATE_USER_AGENT}
    if auth_token:
        if parsed.scheme != "https":
            raise ValueError("A chave privada só pode ser enviada por HTTPS")
        headers["Authorization"] = f"Bearer {auth_token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Manifesto de atualização excede o limite esperado")
    return data


def _clean_sha256(value: str) -> str:
    text = (value or "").strip().lower()
    match = re.search(r"\b([0-9a-f]{64})\b", text)
    if not match:
        raise ValueError("Manifesto não contém SHA-256 válido")
    return match.group(1)


def parse_update_manifest(payload: Mapping[str, Any], *, expected_channel: str | None = None) -> UpdateManifest:
    schema = str(payload.get("schema") or "")
    if schema != MANIFEST_SCHEMA:
        raise ValueError(f"Schema de atualização não suportado: {schema or 'ausente'}")
    app_id = str(payload.get("app_id") or "")
    if app_id != APP_ID:
        raise ValueError("Manifesto pertence a outro aplicativo")
    channel = str(payload.get("channel") or "stable").lower()
    if channel not in {"stable", "beta"}:
        raise ValueError("Canal do manifesto é inválido")
    if expected_channel and channel != expected_channel.lower():
        raise ValueError("Manifesto não corresponde ao canal selecionado")
    version = str(payload.get("version") or "").strip().lstrip("vV")
    if not version:
        raise ValueError("Manifesto não informa a versão")
    package = payload.get("package") or payload.get("asset") or {}
    if not isinstance(package, Mapping):
        raise ValueError("Manifesto não contém pacote de atualização válido")
    package_url = str(package.get("url") or package.get("download_url") or "").strip()
    if not package_url:
        raise ValueError("Manifesto não informa a URL do pacote")
    parsed = urlparse(package_url)
    if parsed.scheme not in {"https", "file"}:
        if not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("Pacote de atualização deve usar HTTPS")
    sha256 = _clean_sha256(str(package.get("sha256") or payload.get("sha256") or ""))
    size = int(package.get("size") or package.get("bytes") or 0)
    if size < 0 or size > MAX_PACKAGE_BYTES:
        raise ValueError("Tamanho do pacote no manifesto é inválido")
    notes_raw = payload.get("notes") or payload.get("release_notes") or []
    if isinstance(notes_raw, str):
        notes = [line.strip(" •\t") for line in notes_raw.splitlines() if line.strip()]
    elif isinstance(notes_raw, list):
        notes = [str(item).strip() for item in notes_raw if str(item).strip()]
    else:
        notes = []
    signature = payload.get("signature") or {}
    if not isinstance(signature, Mapping):
        signature = {}
    return UpdateManifest(
        schema=schema,
        app_id=app_id,
        channel=channel,
        version=version,
        title=str(payload.get("title") or payload.get("name") or f"Artin Sentinel {version}"),
        notes=notes,
        package_url=package_url,
        sha256=sha256,
        release_url=str(payload.get("release_url") or payload.get("html_url") or ""),
        published_at=str(payload.get("published_at") or ""),
        package_size=size,
        minimum_python=str(payload.get("minimum_python") or "3.12"),
        mandatory=bool(payload.get("mandatory", False)),
        signature_key_id=str(signature.get("key_id") or ""),
        signature_value=str(signature.get("value") or signature.get("signature") or ""),
        raw=dict(payload),
    )


def _canonical_signed_payload(payload: Mapping[str, Any]) -> bytes:
    clean = dict(payload)
    clean.pop("signature", None)
    return json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_trusted_keys(data_directory: Path) -> dict[str, str]:
    """Load optional trusted Ed25519 public keys.

    Keys are intentionally not generated by the application.  The official
    publisher provisions a public key separately; the corresponding private key
    never belongs in an application package.
    """

    path = trusted_keys_path(data_directory)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, Mapping) and isinstance(payload.get("keys"), Mapping):
        payload = payload["keys"]
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): str(v) for k, v in payload.items() if str(k) and str(v)}


def verify_manifest_signature(manifest: UpdateManifest, trusted_keys: Mapping[str, str]) -> bool:
    if not manifest.signature_value:
        return False
    key_id = manifest.signature_key_id
    public_b64 = str(trusted_keys.get(key_id) or "")
    if not public_b64:
        raise ValueError(f"Assinatura usa chave não confiável: {key_id or 'sem key_id'}")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover - dependency diagnostic
        raise RuntimeError("Suporte Ed25519 indisponível no runtime") from exc
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        signature = base64.b64decode(manifest.signature_value)
        public_key.verify(signature, _canonical_signed_payload(manifest.raw or {}))
    except Exception as exc:
        raise ValueError("Assinatura Ed25519 do manifesto é inválida") from exc
    return True


def fetch_update_manifest(
    manifest_base_url: str,
    channel: str = DEFAULT_CHANNEL,
    *,
    timeout: float = 8.0,
    data_directory: Path | None = None,
    require_signature: bool = False,
) -> UpdateManifest:
    url = resolve_manifest_url(manifest_base_url, channel)
    auth_token = load_token(manifest_base_url)
    if auth_token and urlparse(url).netloc != urlparse(manifest_base_url).netloc:
        raise ValueError("O manifesto privado deve estar no servidor configurado")
    raw = _read_url(url, timeout=timeout, auth_token=auth_token)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Manifesto de atualização não é JSON válido") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Manifesto de atualização inválido")
    manifest = parse_update_manifest(payload, expected_channel=channel)
    trusted = load_trusted_keys(data_directory) if data_directory is not None else {}
    verified = verify_manifest_signature(manifest, trusted) if manifest.signature_value else False
    if require_signature and not verified:
        raise ValueError("Este canal exige manifesto assinado, mas a assinatura não pôde ser validada")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(url: str, destination: Path, *, expected_size: int = 0, progress: Callable[[str], None] | None = None, auth_token: str | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "file"}:
        if not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("Download de atualização deve usar HTTPS")
    headers = {"Accept": "application/octet-stream", "User-Agent": UPDATE_USER_AGENT}
    if auth_token:
        if parsed.scheme != "https":
            raise ValueError("A chave privada só pode ser enviada por HTTPS")
        headers["Authorization"] = f"Bearer {auth_token}"
    req = Request(url, headers=headers)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    total = 0
    with _open_update_request(req, timeout=30.0, auth_token=auth_token) as response, part.open("wb") as output:
        header_size = int(response.headers.get("Content-Length") or 0)
        size_hint = expected_size or header_size
        if size_hint > MAX_PACKAGE_BYTES:
            raise ValueError("Pacote de atualização excede o limite permitido")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            total += len(chunk)
            if total > MAX_PACKAGE_BYTES:
                raise ValueError("Pacote de atualização excede o limite permitido")
            if progress:
                if size_hint:
                    pct = min(100, int(total * 100 / size_hint))
                    progress(f"Baixando atualização… {pct}%")
                else:
                    progress(f"Baixando atualização… {total // (1024 * 1024)} MiB")
    if expected_size and total != expected_size:
        part.unlink(missing_ok=True)
        raise ValueError(f"Tamanho do pacote difere do manifesto ({total} != {expected_size})")
    os.replace(part, destination)


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("Pacote ZIP de atualização está vazio")
        for info in infos:
            if _is_zip_symlink(info):
                raise ValueError("Pacote de atualização contém link simbólico não permitido")
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:/", name):
                raise ValueError("Pacote de atualização contém caminho absoluto")
            target = (destination / name).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError("Pacote de atualização tentou sair da pasta temporária") from exc
        archive.extractall(destination)


def find_install_root(extracted_dir: Path) -> Path:
    extracted_dir = Path(extracted_dir)
    direct = extracted_dir / "install.sh"
    if direct.is_file() and (extracted_dir / "pyproject.toml").is_file():
        return extracted_dir
    candidates = []
    for install in extracted_dir.glob("*/install.sh"):
        parent = install.parent
        if (parent / "pyproject.toml").is_file():
            candidates.append(parent)
    if len(candidates) != 1:
        raise ValueError("Não foi possível localizar uma única raiz instalável no pacote")
    return candidates[0]


def _write_helper(stage_dir: Path, install_root: Path, log_path: Path) -> Path:
    helper = stage_dir / "apply-update.sh"
    script = f'''#!/usr/bin/env bash
set -u
PID="${{1:-}}"
LOG={json.dumps(str(log_path))}
ROOT={json.dumps(str(install_root))}
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "--- Artin Sentinel update helper $(date -Is) ---"
if [[ -n "$PID" ]]; then
  for _ in $(seq 1 100); do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  if kill -0 "$PID" 2>/dev/null; then
    echo "Falha: Artin Sentinel não encerrou em até 10 s; atualização cancelada."
    exit 10
  fi
fi
cd "$ROOT" || exit 11
bash ./install.sh
STATUS=$?
echo "Updater finalizado com status $STATUS em $(date -Is)"
exit "$STATUS"
'''
    helper.write_text(script, encoding="utf-8")
    helper.chmod(0o700)
    return helper


def stage_update(
    manifest: UpdateManifest,
    data_directory: Path,
    *,
    progress: Callable[[str], None] | None = None,
    require_signature: bool = False,
    auth_base_url: str | None = None,
) -> StagedUpdate:
    data_directory = Path(data_directory)
    if progress:
        progress("Preparando atualização…")
    trusted = load_trusted_keys(data_directory)
    signature_verified = verify_manifest_signature(manifest, trusted) if manifest.signature_value else False
    if require_signature and not signature_verified:
        raise ValueError("A política atual exige assinatura Ed25519 válida")

    safe_version = re.sub(r"[^0-9A-Za-z._-]+", "-", manifest.version)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    updates_root = data_directory / "updates"
    updates_root.mkdir(parents=True, exist_ok=True)
    stage_dir = updates_root / f"{safe_version}-{timestamp}"
    stage_dir.mkdir(parents=True, exist_ok=False)
    package_path = stage_dir / f"ArtinSentinel-{safe_version}.zip"
    try:
        _download_file(
            manifest.package_url,
            package_path,
            expected_size=manifest.package_size,
            progress=progress,
            auth_token=token_for_download(auth_base_url, manifest.package_url) if auth_base_url else None,
        )
        if progress:
            progress("Verificando SHA-256…")
        actual = sha256_file(package_path)
        if actual.lower() != manifest.sha256.lower():
            raise ValueError("SHA-256 do pacote não confere; atualização bloqueada")
        extracted = stage_dir / "package"
        if progress:
            progress("Validando pacote…")
        safe_extract_zip(package_path, extracted)
        install_root = find_install_root(extracted)
        install_script = install_root / "install.sh"
        install_script.chmod(install_script.stat().st_mode | stat.S_IXUSR)
        log_path = data_directory / "logs" / f"update-{safe_version}-{timestamp}.log"
        helper = _write_helper(stage_dir, install_root, log_path)
        (stage_dir / "verified-manifest.json").write_text(
            json.dumps(manifest.raw or {}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if progress:
            progress("Pacote verificado e pronto para instalar")
        return StagedUpdate(
            version=manifest.version,
            title=manifest.title,
            stage_dir=str(stage_dir),
            package_path=str(package_path),
            install_root=str(install_root),
            helper_path=str(helper),
            log_path=str(log_path),
            signature_verified=signature_verified,
        )
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def launch_staged_update(staged: StagedUpdate, current_pid: int) -> int:
    helper = Path(staged.helper_path)
    if not helper.is_file():
        raise FileNotFoundError("Helper de atualização não encontrado")
    log = Path(staged.log_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    # The helper redirects its own stdout/stderr.  start_new_session keeps it
    # alive after the GUI closes.
    proc = subprocess.Popen(
        ["/bin/bash", str(helper), str(int(current_pid))],
        cwd=str(Path(staged.stage_dir)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return int(proc.pid)


def mark_checked(data_directory: Path, settings: UpdateSettings, version: str = "") -> UpdateSettings:
    settings.last_checked_at = datetime.now(timezone.utc).isoformat()
    if version:
        settings.last_seen_version = version
    save_update_settings(data_directory, settings)
    return settings


def should_check_on_startup(settings: UpdateSettings, *, now: datetime | None = None) -> bool:
    if not settings.check_on_startup or not settings.manifest_base_url:
        return False
    if not settings.last_checked_at:
        return True
    try:
        last = datetime.fromisoformat(settings.last_checked_at.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - last).total_seconds() >= STARTUP_CHECK_INTERVAL_HOURS * 3600
