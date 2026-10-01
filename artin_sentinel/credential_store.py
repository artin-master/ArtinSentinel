from __future__ import annotations

from dataclasses import dataclass


SERVICE_NAME = "Artin Sentinel"


@dataclass(slots=True)
class CredentialResult:
    ok: bool
    message: str = ""


class CredentialStore:
    """Secure credential storage backed by the desktop keyring.

    Passwords are never written to SQLite and there is deliberately no plain-text
    fallback. When no usable keyring backend exists, the application keeps the
    password only in memory for the current session.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name
        self._keyring = None
        self._error = ""
        try:
            import keyring  # type: ignore
            self._keyring = keyring
            backend = keyring.get_keyring()
            priority = getattr(backend, "priority", 0)
            if priority is None or float(priority) <= 0:
                self._error = "Nenhum cofre seguro compatível está disponível nesta sessão."
        except Exception as exc:  # pragma: no cover - platform dependent
            self._error = f"Keyring indisponível: {type(exc).__name__}"

    @staticmethod
    def account_for_device(device_id: int) -> str:
        return f"device:{int(device_id)}"

    @property
    def available(self) -> bool:
        return self._keyring is not None and not self._error

    @property
    def status_message(self) -> str:
        return self._error or "Cofre seguro disponível"

    def get_password(self, device_id: int) -> str | None:
        if not self.available:
            return None
        try:
            return self._keyring.get_password(self.service_name, self.account_for_device(device_id))
        except Exception as exc:  # pragma: no cover - backend dependent
            self._error = f"Falha ao ler o cofre seguro: {type(exc).__name__}"
            return None

    def set_password(self, device_id: int, password: str) -> CredentialResult:
        if not self.available:
            return CredentialResult(False, self.status_message)
        try:
            self._keyring.set_password(self.service_name, self.account_for_device(device_id), password)
            return CredentialResult(True, "Credencial salva no cofre seguro do sistema.")
        except Exception as exc:  # pragma: no cover - backend dependent
            self._error = f"Falha ao gravar no cofre seguro: {type(exc).__name__}"
            return CredentialResult(False, self._error)

    def delete_password(self, device_id: int) -> CredentialResult:
        if not self.available:
            return CredentialResult(False, self.status_message)
        try:
            self._keyring.delete_password(self.service_name, self.account_for_device(device_id))
            return CredentialResult(True, "Credencial removida do cofre seguro.")
        except Exception as exc:  # pragma: no cover - backend dependent
            # Deleting a non-existing secret should not block the workflow.
            name = type(exc).__name__
            if "PasswordDeleteError" in name:
                return CredentialResult(True, "Nenhuma credencial salva para remover.")
            self._error = f"Falha ao remover do cofre seguro: {name}"
            return CredentialResult(False, self._error)
