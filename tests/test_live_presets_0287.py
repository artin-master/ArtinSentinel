from artin_sentinel.db import Database


def test_named_live_presets_survive_restart_and_are_independent(tmp_path):
    path = tmp_path / "sentinel.sqlite"
    db = Database(path)
    site = db.ensure_default_site()
    if isinstance(site, dict):
        site = site["id"]
    if site is None:
        site = db.list_sites()[0]["id"]
    db.save_live_workspace(site, 4, [{"channel_id": 1}], False)
    db.save_live_preset(site, "Entrada", 4, [{"channel_id": 2}, {}])
    db.save_live_preset(site, "Pátio", 9, [{"channel_id": 3}])
    assert db.load_live_preset(site, "entrada")["slots"][0]["channel_id"] == 2
    assert db.load_live_workspace(site)["slots"][0]["channel_id"] == 1
    db.conn.close()

    reopened = Database(path)
    assert [row["name"] for row in reopened.list_live_presets(site)] == ["Entrada", "Pátio"]
    reopened.save_live_preset(site, "ENTRADA", 1, [{}])
    assert len(reopened.list_live_presets(site)) == 2
    reopened.delete_live_preset(site, "Pátio")
    assert reopened.load_live_preset(site, "Pátio") is None
    assert reopened.load_live_workspace(site)["grid_count"] == 4
