import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from artin_sentinel.private_update_auth import origin, token_for_download
from artin_sentinel.updater import _NoPrivateRedirect, _read_url
from tools.private_update_origin import authorized, handler_for, issue_client, publish_local, revoke_client


def test_client_isolation_and_revocation(tmp_path):
    first = issue_client(tmp_path, "customer_a")
    second = issue_client(tmp_path, "customer_b")
    assert first != second and authorized(tmp_path, first) and authorized(tmp_path, second)
    assert first not in (tmp_path / "clients.json").read_text()
    revoke_client(tmp_path, "customer_a")
    assert not authorized(tmp_path, first)
    assert authorized(tmp_path, second)


def test_server_requires_bearer_for_manifest_and_package(tmp_path):
    archive = tmp_path / "ArtinSentinel_0.2.60_test.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("pkg/artin_sentinel/__init__.py", '__version__ = "0.2.60"')
        out.writestr("pkg/install.sh", "#!/bin/sh\n")
    manifest = publish_local(tmp_path, archive, "https://updates.example.test")
    token = issue_client(tmp_path, "customer_a")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(tmp_path))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(base + "/sentinel/stable.json")
        assert denied.value.code == 401
        for route in ("/sentinel/stable.json", "/packages/" + archive.name):
            req = Request(base + route, headers={"Authorization": "Bearer " + token})
            with urlopen(req) as response:
                body = response.read()
            assert body
            if route.endswith(".json"):
                assert json.loads(body)["package"]["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
            else:
                assert body == archive.read_bytes()
        with pytest.raises(HTTPError) as traversal:
            urlopen(Request(base + "/packages/../clients.json", headers={"Authorization": "Bearer " + token}))
        assert traversal.value.code == 404
        revoke_client(tmp_path, "customer_a")
        with pytest.raises(HTTPError) as revoked:
            urlopen(Request(base + "/sentinel/stable.json", headers={"Authorization": "Bearer " + token}))
        assert revoked.value.code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_private_token_stays_with_manifest_host(monkeypatch):
    monkeypatch.setattr("artin_sentinel.private_update_auth.load_token", lambda url: "test-secret")
    assert token_for_download("https://updates.example.test", "https://updates.example.test/packages/test.zip") == "test-secret"
    with pytest.raises(ValueError, match="mesmo servidor"):
        token_for_download("https://updates.example.test", "https://foreign.example.test/test.zip")
    with pytest.raises(ValueError):
        origin("http://updates.example.test")
    with pytest.raises(ValueError, match="HTTPS"):
        _read_url("http://127.0.0.1:9999/sentinel/stable.json", auth_token="secret")
    with pytest.raises(ValueError, match="Redirecionamento"):
        _NoPrivateRedirect().redirect_request(None, None, 302, "", {}, "https://foreign.example.test")
