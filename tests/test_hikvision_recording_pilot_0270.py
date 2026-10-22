import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from artin_sentinel.hik_recording import search_hikvision_recordings, hikvision_playback_url
from artin_sentinel.recording_search import Recording


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *_args): pass
    def read(self, *_args):
        return b'''<CMSearchResult xmlns="http://www.hikvision.com/ver20/XMLSchema"><responseStatusStrg>OK</responseStatusStrg><matchList><searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-09-29T12:00:00Z</startTime><endTime>2026-09-29T12:05:00Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>rtsp://192.168.0.247/Streaming/tracks/101/?starttime=20260929T120000Z&amp;endtime=20260929T120500Z&amp;name=segment</playbackURI></mediaSegmentDescriptor></searchMatchItem></matchList></CMSearchResult>'''


class FakeOpener:
    def __init__(self): self.request = None
    def open(self, request, timeout):
        self.request = request
        return FakeResponse()


class HikRecordingPilotTest(unittest.TestCase):
    def test_search_uses_isapi_and_returned_segment(self):
        opener = FakeOpener()
        with patch('artin_sentinel.hik_recording._local_time', side_effect=lambda value: datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')):
            result = search_hikvision_recordings('http://192.0.2.1', 'admin', 'secret', 1,
                                                   datetime(2026, 9, 29, 12), datetime(2026, 9, 29, 13), opener=opener)
        self.assertEqual(len(result.recordings), 1)
        self.assertEqual(result.recordings[0].channel, 1)
        self.assertIn(b'<trackID>101</trackID>', opener.request.data)
        self.assertEqual(opener.request.get_method(), 'POST')
        row = result.recordings[0]
        url = hikvision_playback_url(row, 'http://192.0.2.1', datetime(2026, 9, 29, 12, 1),
                                     datetime(2026, 9, 29, 12, 2), port=10554)
        self.assertIn('192.0.2.1:10554', url)
        self.assertIn('starttime=20260929T120100Z', url)
        self.assertNotIn('192.168.0.247', url)


if __name__ == '__main__': unittest.main()
