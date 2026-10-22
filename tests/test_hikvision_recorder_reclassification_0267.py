"""A DVR mistaken for a camera must route to recorder enumeration."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from artin_sentinel.ip_camera import scan_direct_camera_streams


class HikvisionRecorderReclassificationTest(unittest.TestCase):
    @patch('artin_sentinel.native_protocols.probe_hikvision_isapi_video_inputs')
    @patch('artin_sentinel.native_protocols.probe_hikvision_isapi_device_info')
    @patch('artin_sentinel.ip_camera.read_onvif_device_information')
    def test_sixteen_physical_inputs_are_not_one_camera(self, onvif, info, inputs):
        onvif.return_value = {'manufacturer': 'Hikvision', 'model': 'Hikvision'}
        info.return_value = SimpleNamespace(model='DS-7216HGHI-F1', manufacturer='Hikvision', firmware='V3.4.88')
        inputs.return_value = SimpleNamespace(ok=True, inputs=tuple(range(16)))
        result = scan_direct_camera_streams('192.0.2.1', 'admin', 'example', provider='hikvision')
        self.assertTrue(result.recorder_detected)
        self.assertEqual(result.recorder_channel_hint, 16)
        self.assertEqual(result.model, 'DS-7216HGHI-F1')
        self.assertEqual(result.channels, [])


if __name__ == '__main__':
    unittest.main()
