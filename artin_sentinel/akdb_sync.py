from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError


from artin_akdb import SharedAkdbStore, bundle_delta, bundle_change_preview, validate_manifest
from . import __version__
from .paths import data_dir

DEFAULT_AKDB_MANIFEST_URL = os.environ.get(
    "ARTIN_AKDB_MANIFEST_URL",
    "https://raw.githubusercontent.com/artin-master/ArtinUpdates/main/akdb/stable.json",
).strip()
DEFAULT_GITHUB_REPO = "artin-master/ArtinUpdates"
DEFAULT_GITHUB_BRANCH = "main"
DEFAULT_GITHUB_INBOX = "akdb/inbox"
SETTINGS_SCHEMA = "artin-akdb-sync-settings-v1"
TOKEN_SERVICE = "artin-akdb-github-submission"
TOKEN_ACCOUNT = "submission-token"
USER_AGENT = f"Artin-Sentinel-AKDB-Sync/{__version__}"
MAX_MANIFEST_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 16 * 1024 * 1024


@dataclass(slots=True)
class AkdbSyncSettings:
    manifest_url: str = DEFAULT_AKDB_MANIFEST_URL
    check_with_app_updates: bool = True
    github_repo: str = DEFAULT_GITHUB_REPO
    github_branch: str = DEFAULT_GITHUB_BRANCH
    github_inbox: str = DEFAULT_GITHUB_INBOX
    auto_submit: bool = False


def settings_path(root: Path | None = None) -> Path:
    root = Path(root or data_dir())
    return root / "akdb-sync-settings.json"


def load_settings(root: Path | None = None) -> AkdbSyncSettings:
    path = settings_path(root)
    defaults = AkdbSyncSettings()
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    return AkdbSyncSettings(
        manifest_url=str(payload.get("manifest_url") or defaults.manifest_url).strip(),
        check_with_app_updates=bool(payload.get("check_with_app_updates", defaults.check_with_app_updates)),
        github_repo=str(payload.get("github_repo") or defaults.github_repo).strip(),
        github_branch=str(payload.get("github_branch") or defaults.github_branch).strip(),
        github_inbox=str(payload.get("github_inbox") or defaults.github_inbox).strip().strip("/"),
        # Old installations may have enabled unattended submissions. A field
        # proposal now requires an explicit review and selection every time.
        auto_submit=False,
    )


def save_settings(settings: AkdbSyncSettings, root: Path | None = None) -> Path:
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SETTINGS_SCHEMA, **asdict(settings)}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def set_submission_token(token: str) -> None:
    import keyring
    token = str(token or "").strip()
    if token:
        keyring.set_password(TOKEN_SERVICE, TOKEN_ACCOUNT, token)
    else:
        try:
            keyring.delete_password(TOKEN_SERVICE, TOKEN_ACCOUNT)
        except Exception:
            pass


def get_submission_token() -> str:
    try:
        import keyring
        return str(keyring.get_password(TOKEN_SERVICE, TOKEN_ACCOUNT) or "")
    except Exception:
        return ""


def _read_url(url: str, *, max_bytes: int, timeout: float = 8.0, accept: str = "application/json") -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "file"}:
        if not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("AKDB official source must use HTTPS")
    req = Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("AKDB payload exceeds expected size")
    return data


def fetch_manifest(url: str = DEFAULT_AKDB_MANIFEST_URL) -> dict[str, Any]:
    payload = json.loads(_read_url(url, max_bytes=MAX_MANIFEST_BYTES).decode("utf-8"))
    errors = validate_manifest(payload)
    if errors:
        raise ValueError("invalid AKDB manifest: " + "; ".join(errors))
    return dict(payload)


def fetch_bundle(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    descriptor = manifest.get("bundle") or {}
    url = str(descriptor.get("url") or "")
    inline = str(descriptor.get("data_gzip_base64") or "").strip()
    expected = str(descriptor.get("sha256") or "").lower()
    if inline:
        try:
            compressed = base64.b64decode(inline, validate=True)
            data = gzip.decompress(compressed)
        except Exception as exc:
            raise ValueError(f"AKDB inline bundle is invalid: {exc}") from exc
        if len(data) > MAX_BUNDLE_BYTES:
            raise ValueError("AKDB inline bundle exceeds expected size")
    else:
        data = _read_url(url, max_bytes=MAX_BUNDLE_BYTES)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("AKDB bundle SHA-256 mismatch")
    size = int(descriptor.get("size") or 0)
    if size and len(data) != size:
        raise ValueError("AKDB bundle size mismatch")
    return json.loads(data.decode("utf-8")), digest


def check_official_update(*, store_path: str | Path | None = None, manifest_url: str = DEFAULT_AKDB_MANIFEST_URL) -> dict[str, Any]:
    manifest = fetch_manifest(manifest_url)
    bundle, digest = fetch_bundle(manifest)
    with SharedAkdbStore(store_path) as store:
        state = store.official_release_state()
        delta = bundle_delta(store, bundle)
        preview = bundle_change_preview(store, bundle)
        remote_revision = int(manifest.get("release_revision") or 0)
        meaningful_changes = any(int(delta.get(key) or 0) > 0 for key in (
            "new_records", "updated_records", "conflicts", "new_extensions", "updated_extensions", "extension_conflicts"
        ))
        local_revision = int(state.get("release_revision") or 0)
        revision_changed = remote_revision > local_revision
        same_revision_mismatch = bool(
            remote_revision == local_revision and state.get("bundle_sha256")
            and digest != str(state["bundle_sha256"])
        )
        conflicts = int(delta["conflicts"]) + int(delta["extension_conflicts"])
        blocked_reason = (
            "A fonte ofereceu uma revisão anterior à instalada." if remote_revision < local_revision else
            "A mesma revisão oficial possui conteúdo diferente." if same_revision_mismatch else
            f"Há {conflicts} conflito(s) de mesma revisão para analisar antes da atualização." if conflicts else ""
        )
        available = bool(revision_changed and meaningful_changes and not blocked_reason)
        if revision_changed and not meaningful_changes and not blocked_reason:
            # A release can establish/re-sign the baseline without changing knowledge.
            # Record the official revision silently so the user is only prompted for real additions/edits.
            store.mark_official_release(remote_revision, digest)
            state = store.official_release_state()
        store.mark_official_check(int(bundle.get("core_revision") or 0))
    return {"manifest": manifest, "bundle": bundle, "bundle_sha256": digest,
            "available": available, "delta": delta, "preview": preview,
            "local": state, "blocked_reason": blocked_reason}


def apply_official_update(result: Mapping[str, Any], *, store_path: str | Path | None = None) -> dict[str, Any]:
    manifest = dict(result.get("manifest") or {})
    bundle = dict(result.get("bundle") or {})
    digest = str(result.get("bundle_sha256") or "")
    expected = str((manifest.get("bundle") or {}).get("sha256") or "")
    if expected and digest != expected:
        raise ValueError("AKDB review digest does not match the manifest")
    with SharedAkdbStore(store_path) as store:
        applied = store.apply_official_bundle(
            bundle,
            release_revision=int(manifest.get("release_revision") or 0),
            bundle_sha256=digest,
        )
        return {**applied, "pending_submissions": store.pending_submission_count(), "conflicts": store.conflict_count()}


_SENSITIVE_KEYS = (
    "password", "passwd", "secret", "token", "credential", "username", "user_name",
    "ip", "ip_address", "address", "mac", "serial", "uuid", "endpoint", "web_url", "rtsp_url", "url", "uri",
)
_IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_MAC_RE = re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")
_URL_RE = re.compile(r"(?i)\b(?:https?|rtsp|rtsps)://[^\s]+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_RE = re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+")
_IPV6_RE = re.compile(r"(?i)(?<![\w:])(?:[0-9a-f]{1,4}:){2,}[0-9a-f:.]*(?![\w:])")
_EXTRA_PRIVATE_KEYS = {"hostname", "host_name", "user", "email", "unit_id", "device_id", "api_key", "auth", "authorization", "ipv6", "location"}


def sanitize_for_submission(value: Any, *, key: str = "") -> Any:
    folded = key.casefold()
    if folded in _EXTRA_PRIVATE_KEYS or any(token == folded or folded.endswith("_" + token) for token in _SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(k): sanitize_for_submission(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_submission(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_submission(item) for item in value]
    if isinstance(value, str):
        text = _URL_RE.sub("[redacted-url]", value)
        text = _MAC_RE.sub("[redacted-mac]", text)
        text = _IPV4_RE.sub("[redacted-ip]", text)
        text = _IPV6_RE.sub("[redacted-ip]", text)
        text = _EMAIL_RE.sub("[redacted-email]", text)
        text = _SECRET_RE.sub("[redacted-secret]", text)
        return text
    return value


def pending_proposals(*, store_path: str | Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return the exact sanitized payload available for an operator to review."""
    proposals = []
    with SharedAkdbStore(store_path) as store:
        for item in store.pending_submissions(limit=limit):
            report = sanitize_for_submission(item["report"])
            digest = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            identity = report.get("identity") or {}
            stable_id = str(identity.get("stable_id") or "").strip()
            manufacturer = str(identity.get("observed_manufacturer") or identity.get("manufacturer") or "").strip()
            model = str(identity.get("observed_model") or identity.get("model") or "").strip()
            matches = []
            if stable_id:
                matches = store.conn.execute("SELECT stable_id,manufacturer,model,revision FROM records WHERE stable_id=?", (stable_id,)).fetchall()
            if not matches and manufacturer and model:
                matches = store.conn.execute(
                    "SELECT stable_id,manufacturer,model,revision FROM records WHERE lower(trim(manufacturer))=? AND lower(trim(model))=?",
                    (manufacturer.casefold(), model.casefold()),
                ).fetchall()
            comparison = "nova identidade" if not matches else "correspondência ambígua" if len(matches) > 1 else "identidade existente"
            official = [dict(row) for row in matches]
            changes = []
            if len(official) == 1:
                known = official[0]
                for field, value in (("manufacturer", manufacturer), ("model", model)):
                    if value and value.casefold() != str(known[field]).casefold():
                        changes.append(field)
                provider = str((report.get("domain_data") or {}).get("provider") or "").strip()
                extension = store.conn.execute(
                    "SELECT payload_json FROM domain_extensions WHERE stable_id=? AND domain='sentinel'",
                    (known["stable_id"],),
                ).fetchone()
                if extension and provider:
                    official_provider = str(json.loads(extension["payload_json"]).get("provider") or "")
                    if official_provider and provider.casefold() != official_provider.casefold():
                        changes.append("provider")
            proposals.append({
                "report_id": int(item["report_id"]), "state": item["state"],
                "created_at": item["created_at"], "manufacturer": manufacturer, "model": model,
                "comparison": comparison, "changed_fields": changes, "official": official,
                "report": report, "review_sha256": digest,
            })
    return proposals


def export_proposals(path: str | Path, proposals: list[Mapping[str, Any]]) -> Path:
    """Write a review package; exporting never changes the local queue."""
    if not proposals:
        raise ValueError("Selecione pelo menos um candidato.")
    selected = []
    for item in proposals:
        report = sanitize_for_submission(item["report"])
        digest = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != item["review_sha256"]:
            raise ValueError("A proposta mudou desde a revisão; abra a lista novamente.")
        selected.append({"comparison": item["comparison"], "changed_fields": item["changed_fields"],
                         "official": item["official"], "report": report, "review_sha256": digest})
    out = Path(path)
    if out.exists():
        raise FileExistsError("O arquivo da proposta já existe; escolha outro nome.")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "artin-akdb-contribution-v1", "review_state": "proposal",
                   "candidates": selected}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return out


def _github_api_url(repo: str, path: str) -> str:
    if repo.count("/") != 1:
        raise ValueError("GitHub repository must use owner/repo")
    owner, name = repo.split("/", 1)
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents/{encoded_path}"


def submit_report_to_github(*, report: Mapping[str, Any], report_id: int, content_hash: str,
                            settings: AkdbSyncSettings, token: str) -> str:
    token = str(token or "").strip()
    if not token:
        raise RuntimeError("GitHub submission token is not configured")
    sanitized = sanitize_for_submission(dict(report))
    digest = str(content_hash or hashlib.sha256(json.dumps(sanitized, sort_keys=True).encode()).hexdigest())
    app = re.sub(r"[^a-zA-Z0-9._-]+", "-", str((sanitized.get("source") or {}).get("app") or "artin"))
    filename = f"{int(report_id):06d}-{digest[:16]}.json"
    path = f"{settings.github_inbox.strip('/')}/{app}/{filename}"
    body = {
        "message": f"AKDB field candidate {app} #{int(report_id)}",
        "content": base64.b64encode((json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        "branch": settings.github_branch,
    }
    req = Request(
        _github_api_url(settings.github_repo, path),
        data=json.dumps(body).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=12.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub HTTP {exc.code}: {detail[:600]}") from exc
    content = payload.get("content") or {}
    commit = payload.get("commit") or {}
    return str(content.get("html_url") or commit.get("html_url") or path)


def submit_pending(*, store_path: str | Path | None = None, settings: AkdbSyncSettings | None = None,
                   token: str | None = None, reviewed: Mapping[int, str] | None = None,
                   limit: int = 20) -> dict[str, Any]:
    if not reviewed:
        raise ValueError("Revise e selecione os candidatos antes do envio.")
    settings = settings or load_settings()
    token = get_submission_token() if token is None else token
    submitted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    with SharedAkdbStore(store_path) as store:
        items = [item for item in store.pending_submissions(limit=max(limit, store.pending_submission_count()))
                 if int(item["report_id"]) in reviewed][:limit]
        if len(items) != len(reviewed):
            raise ValueError("A fila mudou durante a revisão. Abra a lista novamente.")
        for item in items:
            sanitized = sanitize_for_submission(item["report"])
            digest = hashlib.sha256(json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if digest != reviewed[int(item["report_id"])]:
                raise ValueError("O conteúdo mudou durante a revisão. Abra a lista novamente.")
            try:
                remote_ref = submit_report_to_github(
                    report=sanitized, report_id=int(item["report_id"]),
                    content_hash=str(item.get("content_hash") or ""), settings=settings, token=token,
                )
                store.mark_submission_result(int(item["queue_id"]), remote_ref=remote_ref)
                submitted.append({"report_id": int(item["report_id"]), "remote_ref": remote_ref})
            except Exception as exc:
                store.mark_submission_result(int(item["queue_id"]), error=f"{type(exc).__name__}: {exc}")
                failed.append({"report_id": int(item["report_id"]), "error": f"{type(exc).__name__}: {exc}"})
        state = store.sync_state(domain="sentinel")
    return {"submitted": submitted, "failed": failed, "state": state}
