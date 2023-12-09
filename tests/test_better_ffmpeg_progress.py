from unittest import TestCase
from unittest.mock import patch, MagicMock, mock_open
import io
from better_ffmpeg_progress import FfmpegProcess, ffmpeg_process

# pyright:reportPrivateUsage=false


class TestFfmpegProgress(TestCase):
    @patch("subprocess.run")
    def test_ffmpeg_process(self, mock_run):
        with self.assertRaises(ValueError):  # lack '-i'
            ffmpeg_process("ffmpeg")
        with self.assertRaises(ValueError):  # lack output_file_path
            ffmpeg_process("ffmpeg -i test_in.mp4")

    @patch("subprocess.Popen")
    def test_run(self, mock_Popen: MagicMock):
        # mock subprocess.run, _set_duration need
        stdout, stderr = 0, 1
        mock_process = mock_Popen.return_value.__enter__.return_value
        mock_process.communicate.return_value = stdout, stderr

        process = FfmpegProcess("ffmpeg -i test_in.mp4 test_out.mp4", hide_tips=True)

        # mock subprocess.Popen
        mock_process.poll.return_value = None  # skip Popen read
        mock_process.returncode.return_value = 1  # caused Error

        with self.assertRaises(RuntimeError):
            process.run()

    @patch("builtins.input")
    @patch("pathlib.Path.exists")
    @patch("subprocess.run")
    def test__should_overwrite(self, mock_run, mock_exists: MagicMock, mock_input: MagicMock):
        mock_exists.return_value = False

        # file not exists, can overwrite
        process = FfmpegProcess("ffmpeg -i test_in.mp4 test_out.mp4")
        self.assertTrue(process._can_overwrite())

        mock_exists.return_value = True

        # file exists, but user provide '-n', can not overwrite
        process = FfmpegProcess("ffmpeg -i test_in.mp4 test_out.mp4 -n", hide_tips=True)
        with self.assertRaises(FileExistsError):
            process._can_overwrite()

        # file exists, user provide '-y',but input 'N', can not overwrite
        process = FfmpegProcess("ffmpeg -i test_in.mp4 test_out.mp4", hide_tips=True)
        mock_input.return_value = "N"
        with self.assertRaises(FileExistsError):
            process._can_overwrite()

    @patch("builtins.open")
    @patch("subprocess.run")
    def test__iter_if_concat(self, mock_run, mock_open_: MagicMock):
        process = FfmpegProcess(
            "ffmpeg -i test_in_1.mp4 -i test_in_2.mp4 test_out.mp4", hide_tips=True
        )
        self.assertListEqual(list(process._iter_if_concat()), ["test_in_1.mp4", "test_in_2.mp4"])

        mock_open(mock_open_, "file 'test_in_1.mp4'\nfile 'test_in_2.mp4'")
        process = FfmpegProcess("ffmpeg -f concat -i test.txt test_out.mp4", hide_tips=True)
        self.assertListEqual(list(process._iter_if_concat()), ["test_in_1.mp4", "test_in_2.mp4"])
