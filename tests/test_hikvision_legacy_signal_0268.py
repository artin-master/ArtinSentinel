"""Legacy Hikvision XML without videoInputEnabled still warrants RTSP validation."""
import unittest
from unittest.mock import patch

from artin_sentinel.native_protocols import probe_hikvision_isapi_video_inputs


class HikvisionLegacySignalTest(unittest.TestCase):
    @patch('artin_sentinel.native_protocols._hikvision_isapi_get')
    def test_missing_enabled_is_unknown_not_disabled(self, get):
        get.return_value = (200, b'<VideoInputChannelList><VideoInputChannel><id>1</id><name>CAM 1</name></VideoInputChannel><VideoInputChannel><id>2</id><videoInputEnabled>false</videoInputEnabled><resDesc>NO VIDEO</resDesc></VideoInputChannel></VideoInputChannelList>', 'http://example', 'OK')
        inventory = probe_hikvision_isapi_video_inputs('192.0.2.1', 'admin', 'secret')
        self.assertTrue(inventory.ok)
        self.assertIsNone(inventory.inputs[0].enabled)
        self.assertFalse(inventory.inputs[1].enabled)
        self.assertIn('1 com sinal', inventory.detail)


if __name__ == '__main__':
    unittest.main()
