import unittest
from types import SimpleNamespace
from unittest.mock import patch

from artin_sentinel.recorder import diagnose_hikvision_routes


class HikvisionRouteDiagnosticsTest(unittest.TestCase):
    @patch('artin_sentinel.recorder.probe_rtsp_url_detailed')
    def test_main_sub_per_channel_respects_port_and_reports_failure(self, probe):
        def reply(url, *_args, **_kwargs):
            return SimpleNamespace(ok=url.endswith('/101'), detail='RTSP 404',
                                   safe_summary=lambda: 'SDP OK' if url.endswith('/101') else 'RTSP 404')
        probe.side_effect = reply
        results = diagnose_hikvision_routes('192.0.2.1', 'admin', 'secret', [2, 1], rtsp_port=10554)
        self.assertEqual(len(results), 4)
        self.assertEqual([row[:2] for row in results], [(1, 'Main'), (1, 'Sub'), (2, 'Main'), (2, 'Sub')])
        self.assertEqual(results[0][2], 'RTSP/SDP OK')
        self.assertEqual(results[1][3], 'RTSP 404')
        self.assertTrue(all(':10554/' in call.args[0] for call in probe.call_args_list))
        self.assertNotIn('secret', str(results))


if __name__ == '__main__':
    unittest.main()
