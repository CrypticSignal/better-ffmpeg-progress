from unittest import TestCase
from unittest.mock import patch

from better_ffmpeg_progress import FfmpegProcess, ffmpeg_process


class TestFfmpegProgress(TestCase):
    @patch("subprocess.run")
    def test_ffmpeg_process(self, mock_run):
        with self.assertRaises(ValueError):
            ffmpeg_process("ffmpeg")

    @patch("subprocess.run")
    def test_FfmpegProcess(self, mock_run):
        with self.assertRaises(ValueError):
            FfmpegProcess("ffmpeg")

    @patch("subprocess.run")
    def test__should_overwrite(self):
        process = FfmpegProcess("-i")
        self.assertTrue(process._should_overwrite())  # type:ignore
