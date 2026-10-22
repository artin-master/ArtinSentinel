from artin_sentinel.log_viewer import filter_log_lines, read_log_tail


def test_log_tail_limits_and_redacts_credentials(tmp_path):
    log = tmp_path / "rtsp-diagnostics.log"
    log.write_text("discard\n" * 200 + "rtsp://admin:private@192.0.2.3/live token=abcdef\n401 Unauthorized\n")
    text = read_log_tail(tmp_path, "rtsp", max_bytes=200)
    assert text.count("discard") < 30
    assert "private" not in text
    assert "abcdef" not in text
    assert "401 Unauthorized" in filter_log_lines(text, "unauthorized")


def test_log_sources_are_allowlisted(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        read_log_tail(tmp_path, "../private")
    assert "Ainda não há" in read_log_tail(tmp_path, "fault")
