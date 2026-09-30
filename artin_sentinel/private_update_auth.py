"""Per-installation credentials for the private update origin."""

from urllib.parse import urlparse

SERVICE = "artin-sentinel-private-updates"


def origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Atualização privada exige endereço HTTPS sem senha na URL")
    return f"https://{parsed.hostname.lower()}:{parsed.port or 443}"


def store_token(base_url: str, token: str) -> None:
    import keyring
    host = urlparse(base_url).hostname or ""
    if host in {"raw.githubusercontent.com", "github.com", "api.github.com"}:
        raise ValueError("Configure a URL do servidor privado antes de guardar a chave")
    token = token.strip()
    if len(token) < 32 or any(char.isspace() for char in token):
        raise ValueError("Chave de atualização inválida")
    keyring.set_password(SERVICE, origin(base_url), token)


def load_token(base_url: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(SERVICE, origin(base_url))
    except (ValueError, ImportError):
        return None


def token_for_download(base_url: str, package_url: str) -> str | None:
    token = load_token(base_url)
    if token and origin(base_url) != origin(package_url):
        raise ValueError("O pacote privado deve estar no mesmo servidor do manifesto")
    return token
