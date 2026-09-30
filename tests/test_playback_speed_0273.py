import unittest
from unittest.mock import patch

from artin_sentinel.live import LiveStreamSession, LiveAudioSession


class PlaybackSpeedTest(unittest.TestCase):
    def test_eight_and_sixteen_are_applied_to_video_and_audio(self):
        for speed in (8.0, 16.0):
            video = LiveStreamSession("rtsp://127.0.0.1/stream", playback=True, playback_speed=speed)
            audio = LiveAudioSession("rtsp://127.0.0.1/stream", playback=True, playback_speed=speed)
            with patch("artin_sentinel.live.shutil.which", return_value="/usr/bin/ffmpeg"):
                command = video._command(video.url)
                self.assertEqual(command[command.index("-readrate") + 1], f"{speed:g}")
                self.assertIn(f"setpts=PTS/{speed:g}", command[command.index("-vf") + 1])
                with patch("artin_sentinel.live.ffmpeg_audio_output_devices", return_value=frozenset({"pulse"})):
                    commands = audio._commands(audio.url)
                    pulse = next(parts for name, parts in commands if name == "FFmpeg/Pulse-PipeWire")
                    self.assertEqual(pulse[pulse.index("-af") + 1].count("atempo=2"), 3 if speed == 8 else 4)
