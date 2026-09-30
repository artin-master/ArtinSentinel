from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from artin_sentinel.recording_search import RecordingSearchError, search_recordings, playback_rtsp_url


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, _limit):
        return self.text.encode()


class FakeOpener:
    def __init__(self, *, search_answer="OK"):
        self.calls = []
        self.search_answer = search_answer

    def open(self, request, timeout):
        assert timeout <= 5
        params = parse_qs(urlparse(request.full_url).query)
        self.calls.append(params)
        action = params["action"][0]
        values = {
            "factory.create": "result=08137\n",
            "findFile": self.search_answer,
            "findNextFile": "found=1\nitems[0].Channel=0\nitems[0].StartTime=2026-09-28 12:00:00\nitems[0].EndTime=2026-09-28 12:30:00\nitems[0].Type=dav\nitems[0].Length=2048\n",
            "close": "OK", "destroy": "OK",
        }
        return FakeResponse(values[action])


def test_search_uses_documented_read_only_finder_and_cleans_up():
    opener = FakeOpener()
    start = datetime(2026, 9, 28, 12)
    result = search_recordings("http://192.0.2.8/", "admin", "secret", 1, start, start + timedelta(hours=1), opener=opener)
    assert len(result.recordings) == 1
    assert result.recordings[0].size == 2048
    assert result.recordings[0].channel == 1
    assert [x["action"][0] for x in opener.calls] == ["factory.create", "findFile", "findNextFile", "close", "destroy"]
    assert opener.calls[1]["condition.Channel"] == ["1"]
    assert opener.calls[1]["condition.StartTime"] == ["2026-09-28 12:00:00"]


def test_failed_search_still_closes_finder():
    opener = FakeOpener(search_answer="ERROR")
    start = datetime(2026, 9, 28, 12)
    with pytest.raises(RecordingSearchError, match="não iniciou"):
        search_recordings("http://192.0.2.8", "admin", "secret", 1, start, start + timedelta(minutes=30), opener=opener)
    assert [x["action"][0] for x in opener.calls][-2:] == ["close", "destroy"]


def test_period_and_address_are_bounded():
    start = datetime(2026, 9, 28, 12)
    with pytest.raises(RecordingSearchError, match="24 horas"):
        search_recordings("http://192.0.2.8", "u", "p", 1, start, start + timedelta(days=2))
    with pytest.raises(RecordingSearchError, match="inválido"):
        search_recordings("http://u:p@192.0.2.8", "u", "p", 1, start, start + timedelta(minutes=5))


def test_playback_url_uses_documented_local_timestamp_and_selected_channel():
    start = datetime(2026, 9, 28, 19, 42, 0)
    assert playback_rtsp_url("http://192.0.2.8:8080/", 1, start, start + timedelta(minutes=5)) == (
        "rtsp://192.0.2.8:554/cam/playback?channel=1"
        "&starttime=2026_09_28_19_42_00&endtime=2026_09_28_19_47_00"
    )


def test_firmware_result_outside_requested_period_is_ignored():
    class WrongTime(FakeOpener):
        def open(self, request, timeout):
            response = super().open(request, timeout)
            if parse_qs(urlparse(request.full_url).query)["action"] == ["findNextFile"]:
                response.text = response.text.replace("12:00:00", "01:00:00").replace("12:30:00", "01:30:00").replace("Channel=1", "Channel=0")
            return response
    start = datetime(2026, 9, 28, 12)
    result = search_recordings("http://192.0.2.8", "admin", "secret", 1, start, start + timedelta(hours=1), opener=WrongTime())
    assert result.recordings == ()
    assert result.ignored == 1


def test_second_camera_uses_zero_based_response_without_admitting_first_camera():
    class SecondChannel(FakeOpener):
        def open(self, request, timeout):
            response = super().open(request, timeout)
            if parse_qs(urlparse(request.full_url).query)["action"] == ["findNextFile"]:
                response.text = response.text.replace("Channel=0", "Channel=1")
            return response
    start = datetime(2026, 9, 28, 12)
    result = search_recordings("http://192.0.2.8", "admin", "secret", 2, start, start + timedelta(hours=1), opener=SecondChannel())
    assert [r.channel for r in result.recordings] == [2]
    first_camera = search_recordings("http://192.0.2.8", "admin", "secret", 2, start, start + timedelta(hours=1), opener=FakeOpener())
    assert first_camera.recordings == ()
    assert first_camera.ignored == 1
