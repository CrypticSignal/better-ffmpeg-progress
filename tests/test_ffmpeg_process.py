import os
import shutil
import sys
from pathlib import Path

import pytest

from better_ffmpeg_progress import (
    FfmpegCommandError,
    FfmpegProcess,
    FfmpegProcessError,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and FFprobe are required",
)


@pytest.fixture
def input_file(tmp_path: Path) -> Path:
    path = tmp_path / "input.mkv"
    FfmpegProcess(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=2:size=64x64:rate=10",
            "-c:v",
            "ffv1",
            str(path),
        ],
        ffmpeg_log_file=os.devnull,
        duration_override=2,
    ).run()
    return path


@pytest.mark.parametrize("use_tqdm", [False, True])
def test_run_succeeds(input_file: Path, tmp_path: Path, use_tqdm: bool):
    output_file = tmp_path / "output.mkv"
    log_file = tmp_path / "log.txt"
    process = FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", str(output_file)],
        ffmpeg_log_file=log_file,
        use_tqdm=use_tqdm,
    )
    assert process._duration_secs == pytest.approx(2, abs=0.2)
    process.run()
    assert output_file.stat().st_size > 0
    assert log_file.exists()


def test_run_without_duration_does_not_hang(tmp_path: Path):
    # Without a duration, the progress output must still be read, or FFmpeg blocks once the
    # pipe's buffer is full. -stats_period makes FFmpeg write enough output to fill it.
    process = FfmpegProcess(
        [
            "ffmpeg",
            "-stats_period",
            "0.001",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=20:size=32x32:rate=1000",
            "-f",
            "null",
            "-",
        ],
        ffmpeg_log_file=tmp_path / "log.txt",
    )
    assert process._duration_secs is None
    process.run()


def test_failure_includes_log_tail(input_file: Path, tmp_path: Path):
    process = FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "no_such_encoder", str(tmp_path / "o.mkv")],
        ffmpeg_log_file=tmp_path / "log.txt",
    )
    with pytest.raises(FfmpegProcessError, match="no_such_encoder"):
        process.run()


def test_missing_input_file(tmp_path: Path):
    with pytest.raises(FfmpegCommandError, match="Input file not found"):
        FfmpegProcess(["ffmpeg", "-i", str(tmp_path / "missing.mp4"), "out.mp4"])


@pytest.mark.parametrize(
    "input_args",
    [
        ["-i", "-"],
        ["-i", "pipe:0"],
        ["-f", "lavfi", "-i", "testsrc2"],
        ["-i", "rtsp://127.0.0.1:1/stream"],
    ],
)
def test_non_file_inputs_are_accepted(input_args, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    process = FfmpegProcess(["ffmpeg"] + input_args + ["-f", "null", "-"], duration_override=1)
    assert ":" not in process._ffmpeg_log_file.name


def test_image_sequence_input_is_accepted(tmp_path: Path):
    FfmpegProcess(
        ["ffmpeg", "-i", str(tmp_path / "img%03d.png"), "-f", "null", "-"],
        ffmpeg_log_file=os.devnull,
        duration_override=1,
    )


def test_overwrite(input_file: Path, tmp_path: Path):
    output_file = tmp_path / "output.mkv"
    output_file.touch()
    command = ["ffmpeg", "-i", str(input_file), str(output_file)]

    with pytest.raises(FfmpegCommandError, match="already exists"):
        FfmpegProcess(command, overwrite=False)

    with pytest.raises(FfmpegCommandError, match="already exists"):
        FfmpegProcess(command[:-1] + ["-n", str(output_file)])

    process = FfmpegProcess(command, overwrite=True)
    assert "-y" in process._ffmpeg_command

    # -y in the command takes priority over overwrite=False.
    FfmpegProcess(command[:-1] + ["-y", str(output_file)], overwrite=False)


@pytest.mark.skipif(sys.platform == "win32", reason="Uses POSIX signals")
def test_keyboard_interrupt_raises_and_does_not_kill_python(tmp_path: Path):
    import signal
    import threading

    from better_ffmpeg_progress import FfmpegProcessInterruptedError

    process = FfmpegProcess(
        ["ffmpeg", "-re", "-f", "lavfi", "-i", "testsrc2=duration=30", "-f", "null", "-"],
        ffmpeg_log_file=tmp_path / "log.txt",
        duration_override=30,
    )
    timer = threading.Timer(1, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        with pytest.raises(FfmpegProcessInterruptedError):
            process.run()
    finally:
        timer.cancel()
    assert process._process is not None
    assert process._process.poll() is not None
