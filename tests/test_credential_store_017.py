import sys
from types import SimpleNamespace

from artin_sentinel.credential_store import CredentialStore


class FakeBackend:
    priority = 1


class FakeKeyring:
    def __init__(self):
        self.data = {}
    def get_keyring(self):
        return FakeBackend()
    def get_password(self, service, account):
        return self.data.get((service, account))
    def set_password(self, service, account, password):
        self.data[(service, account)] = password
    def delete_password(self, service, account):
        self.data.pop((service, account), None)


def test_credential_store_uses_keyring_only(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    store = CredentialStore("Test Sentinel")
    assert store.available
    assert store.set_password(7, "secret").ok
    assert store.get_password(7) == "secret"
    assert store.delete_password(7).ok
    assert store.get_password(7) is None
