from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from artin_sentinel import recording_search as search
from artin_sentinel.live import LiveStreamSession


class Reply:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, _limit):
        return self.body.encode()


class Recorder:
    def open(self, request, timeout):
        params = parse_qs(urlparse(request.full_url).query)
        action = params["action"][0]
        if action == "factory.create":
            return Reply("result=08137")
        if action == "findFile":
            self.channel = int(params["condition.Channel"][0])
            return Reply("OK")
        if action == "findNextFile":
            return Reply(f"found=1\nitems[0].Channel={self.channel - 1}\n"
                         "items[0].StartTime=2026-09-29 08:00:00\n"
                         "items[0].EndTime=2026-09-29 08:30:00\nitems[0].Type=dav\n")
        return Reply("OK")


def test_mhdx_finder_normalizes_four_channels_without_cross_matching():
    start = datetime(2026, 9, 29, 8)
    for channel in (1, 2, 3, 4):
        result = search.search_recordings("http://192.0.2.8", "u", "p", channel,
                                          start, start + timedelta(hours=1), opener=Recorder())
        assert [clip.channel for clip in result.recordings] == [channel]


def test_aggregator_keeps_healthy_channels_if_one_fails():
    start = datetime(2026, 9, 29, 8)

    def lookup(_url, _user, _password, channel, _start, _end):
        if channel == 3:
            raise search.RecordingSearchError("sem acesso")
        return search.SearchResult((search.Recording(channel, "2026-09-29 08:00:00",
                                                     "2026-09-29 08:30:00", "dav", 20),))

    with patch.object(search, "search_recordings", lookup):
        result = search.search_recordings_multi("http://192.0.2.8", "u", "p",
                                                (1, 2, 3), start, start + timedelta(hours=1))
    assert [clip.channel for clip in result.recordings] == [1, 2]
    assert result.warnings == ("CAM 3: sem acesso",)


def test_requested_playback_speed_is_applied_to_decoder():
    for speed in (0.5, 1, 2, 4):
        session = LiveStreamSession("rtsp://192.0.2.8/cam/playback", playback=True, playback_speed=speed)
        command = session._command(session.url)
        assert command[command.index("-readrate") + 1] == f"{speed:g}"
        assert f"setpts=PTS/{speed:g}" in command[command.index("-vf") + 1]
