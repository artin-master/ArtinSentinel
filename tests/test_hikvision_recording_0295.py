import io
import re
import unittest
from datetime import datetime
from urllib.error import HTTPError
from unittest.mock import patch

from artin_sentinel.hik_recording import (
    search_hikvision_recordings,
    hikvision_playback_url,
)
from artin_sentinel.recording_search import Recording, RecordingSearchError


def result_xml(status, start, end, *, name="segment", size=1234):
    return f"""<CMSearchResult xmlns="http://www.hikvision.com/ver20/XMLSchema">
<responseStatus>true</responseStatus><responseStatusStrg>{status}</responseStatusStrg>
<numOfMatches>1</numOfMatches><matchList><searchMatchItem>
<trackID>101</trackID><timeSpan>
<startTime>{start}</startTime><endTime>{end}</endTime></timeSpan>
<mediaSegmentDescriptor><playbackURI>rtsp://192.0.2.55/Streaming/tracks/101/?starttime={start.replace('-', '').replace(':', '')}&amp;endtime={end.replace('-', '').replace(':', '')}&amp;name={name}&amp;size={size}</playbackURI></mediaSegmentDescriptor>
<metadataDescriptor>motion</metadataDescriptor>
</searchMatchItem></matchList></CMSearchResult>""".encode()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass
    def read(self, *_args):
        return self.payload


class SequenceOpener:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


class ErrorOpener:
    def __init__(self, code):
        self.code = code
    def open(self, request, timeout):
        raise HTTPError(request.full_url, self.code, "secret-password", {}, io.BytesIO())


class HikvisionRecording295Test(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 15, 12, 0, 0)
        self.end = datetime(2026, 10, 15, 13, 0, 0)

    @patch("artin_sentinel.hik_recording._local_time")
    def test_search_reuses_search_id_and_advances_position(self, local_time):
        local_time.side_effect = lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        opener = SequenceOpener([
            result_xml("MORE", "2026-10-15T12:00:00Z", "2026-10-15T12:05:00Z"),
            result_xml("OK", "2026-10-15T12:05:00Z", "2026-10-15T12:10:00Z"),
        ])
        result = search_hikvision_recordings(
            "http://192.0.2.1", "operator", "hidden", 1,
            self.start, self.end, opener=opener,
        )
        self.assertEqual(len(result.recordings), 2)
        bodies = [request.data.decode() for request in opener.requests]
        ids = [re.search(r"<searchID>([^<]+)</searchID>", body).group(1) for body in bodies]
        self.assertEqual(ids[0], ids[1])
        self.assertIn("<searchResultPostion>0</searchResultPostion>", bodies[0])
        self.assertIn("<searchResultPostion>40</searchResultPostion>", bodies[1])
        self.assertIn("<contentType>video</contentType>", bodies[0])
        self.assertIn("//recordType.meta.std-cgi.com", bodies[0])

    @patch("artin_sentinel.hik_recording._local_time")
    def test_search_parses_size_and_deduplicates_repeated_page(self, local_time):
        local_time.side_effect = lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        page = result_xml("MORE", "2026-10-15T12:00:00Z", "2026-10-15T12:05:00Z", size=98765)
        opener = SequenceOpener([page, page])
        result = search_hikvision_recordings(
            "http://192.0.2.1", "operator", "hidden", 1,
            self.start, self.end, opener=opener,
        )
        self.assertEqual(len(result.recordings), 1)
        self.assertEqual(result.recordings[0].size, 98765)
        self.assertTrue(result.warnings)
        self.assertFalse(result.truncated)

    def test_response_status_is_reported_without_private_payload(self):
        class RejectOpener:
            def open(self, request, timeout):
                return FakeResponse(
                    b"<ResponseStatus><statusString>Invalid XML Content</statusString>"
                    b"<subStatusCode>badXmlContent</subStatusCode></ResponseStatus>"
                )
        with self.assertRaises(RecordingSearchError) as ctx:
            search_hikvision_recordings(
                "http://192.0.2.1", "operator", "top-secret", 1,
                self.start, self.end, opener=RejectOpener(),
            )
        self.assertIn("badXmlContent", str(ctx.exception))
        self.assertNotIn("top-secret", str(ctx.exception))

    def test_auth_error_is_sanitized(self):
        with self.assertRaises(RecordingSearchError) as ctx:
            search_hikvision_recordings(
                "http://192.0.2.1", "operator", "top-secret", 1,
                self.start, self.end, opener=ErrorOpener(401),
            )
        message = str(ctx.exception)
        self.assertIn("401/403", message)
        self.assertNotIn("top-secret", message)
        self.assertNotIn("secret-password", message)

    def test_playback_route_uses_enrolled_host_and_keeps_hikvision_query(self):
        recording = Recording(
            1, "2026-10-15 12:00:00", "2026-10-15 12:05:00", "motion", 98765,
            playback_uri=(
                "rtsp://192.0.2.55/Streaming/tracks/101/"
                "?starttime=20261015T150000Z&endtime=20261015T150500Z&name=abc&size=98765"
            ),
        )
        url = hikvision_playback_url(
            recording, "http://198.51.100.9",
            datetime(2026, 10, 15, 12, 1, 0),
            datetime(2026, 10, 15, 12, 2, 0),
            port=10554,
        )
        self.assertIn("rtsp://198.51.100.9:10554/Streaming/tracks/101/", url)
        self.assertIn("starttime=20261015T150100Z", url)
        self.assertIn("endtime=20261015T150200Z", url)
        self.assertIn("name=abc", url)
        self.assertNotIn("192.0.2.55", url)

    def test_playback_route_rejects_embedded_credentials(self):
        recording = Recording(
            1, "2026-10-15 12:00:00", "2026-10-15 12:05:00", "motion", 0,
            playback_uri=(
                "rtsp://user:password@192.0.2.55/Streaming/tracks/101/"
                "?starttime=20261015T150000Z&endtime=20261015T150500Z"
            ),
        )
        with self.assertRaises(RecordingSearchError):
            hikvision_playback_url(
                recording, "http://198.51.100.9",
                datetime(2026, 10, 15, 12, 0, 0),
                datetime(2026, 10, 15, 12, 1, 0),
            )


if __name__ == "__main__":
    unittest.main()
