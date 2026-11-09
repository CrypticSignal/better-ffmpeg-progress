import os
import shutil
import subprocess
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
    # Nothing is detected until run() is called.
    assert process._duration_secs is None
    process.run()
    assert process._duration_secs == pytest.approx(2, abs=0.2)
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
    process.run()
    assert process._duration_secs is None


def test_failure_includes_log_tail(input_file: Path, tmp_path: Path):
    process = FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "no_such_encoder", str(tmp_path / "o.mkv")],
        ffmpeg_log_file=tmp_path / "log.txt",
    )
    # FFmpeg's error wording varies between versions, so only check that the log tail is included.
    with pytest.raises(FfmpegProcessError, match="Last lines of the log:\n."):
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
    command = ["ffmpeg", "-i", str(input_file), "-c", "copy", str(output_file)]
    log_file = tmp_path / "log.txt"

    with pytest.raises(FfmpegCommandError, match="already exists"):
        FfmpegProcess(command, overwrite=False, ffmpeg_log_file=log_file).run()

    with pytest.raises(FfmpegCommandError, match="already exists"):
        FfmpegProcess(command[:-1] + ["-n", str(output_file)], ffmpeg_log_file=log_file).run()
    assert output_file.stat().st_size == 0

    FfmpegProcess(command, overwrite=True, ffmpeg_log_file=log_file).run()
    assert output_file.stat().st_size > 0

    # -y in the command takes priority over overwrite=False.
    FfmpegProcess(
        command[:-1] + ["-y", str(output_file)], overwrite=False, ffmpeg_log_file=log_file
    ).run()


def test_existing_output_other_than_last_does_not_hang(input_file: Path, tmp_path: Path):
    # FFmpeg would ask whether to overwrite first.mkv and wait forever for an answer.
    first = tmp_path / "first.mkv"
    first.touch()
    second = tmp_path / "second.mkv"
    command = ["ffmpeg", "-i", str(input_file), "-c", "copy", str(first)]
    command += ["-c", "copy", str(second)]
    log_file = tmp_path / "log.txt"

    with pytest.raises(FfmpegCommandError, match="already exists"):
        FfmpegProcess(command, ffmpeg_log_file=log_file).run()
    assert first.stat().st_size == 0

    FfmpegProcess(command, overwrite=True, ffmpeg_log_file=log_file).run()
    assert first.stat().st_size > 0


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


def test_progress_callback(input_file: Path, tmp_path: Path):
    calls = []
    FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", str(tmp_path / "out.mkv")],
        ffmpeg_log_file=tmp_path / "log.txt",
        progress_callback=lambda *args: calls.append(args),
    ).run()
    assert calls
    secs, duration, size_mb = calls[-1]
    assert duration == pytest.approx(2, abs=0.2)
    assert 0 <= secs <= duration
    assert size_mb > 0


def test_progress_callback_without_duration(tmp_path: Path):
    calls = []
    FfmpegProcess(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc2=duration=1:size=32x32", "-f", "null", "-"],
        ffmpeg_log_file=tmp_path / "log.txt",
        progress_callback=lambda *args: calls.append(args),
    ).run()
    assert calls
    assert all(duration is None for _, duration, _ in calls)


def test_progress_callback_exception_stops_ffmpeg(tmp_path: Path):
    def callback(secs, duration, size_mb):
        raise RuntimeError("stop")

    process = FfmpegProcess(
        ["ffmpeg", "-re", "-f", "lavfi", "-i", "testsrc2=duration=30", "-f", "null", "-"],
        ffmpeg_log_file=tmp_path / "log.txt",
        duration_override=30,
        progress_callback=callback,
    )
    with pytest.raises(RuntimeError, match="stop"):
        process.run()
    assert process._process is not None
    assert process._process.poll() is not None


def test_quiet(input_file: Path, tmp_path: Path, capsys):
    FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", str(tmp_path / "out.mkv")],
        ffmpeg_log_file=tmp_path / "log.txt",
        duration_override=2,
        quiet=True,
    ).run()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_failure_sets_error_attributes(input_file: Path, tmp_path: Path):
    log_file = tmp_path / "log.txt"
    process = FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "no_such_encoder", str(tmp_path / "o.mkv")],
        ffmpeg_log_file=log_file,
    )
    with pytest.raises(FfmpegProcessError) as exc_info:
        process.run()
    assert exc_info.value.returncode not in (None, 0)
    assert exc_info.value.log_file == log_file


@pytest.mark.parametrize("delete", [False, True])
def test_delete_log_on_success(input_file: Path, tmp_path: Path, delete: bool):
    log_file = tmp_path / "log.txt"
    FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", str(tmp_path / "out.mkv")],
        ffmpeg_log_file=log_file,
        delete_log_on_success=delete,
    ).run()
    assert log_file.exists() != delete


def test_delete_log_on_success_keeps_log_on_failure(input_file: Path, tmp_path: Path):
    log_file = tmp_path / "log.txt"
    with pytest.raises(FfmpegProcessError):
        FfmpegProcess(
            ["ffmpeg", "-i", str(input_file), "-c:v", "no_such_encoder", str(tmp_path / "o.mkv")],
            ffmpeg_log_file=log_file,
            delete_log_on_success=True,
        ).run()
    assert log_file.exists()


def test_delete_log_on_success_never_deletes_devnull(input_file: Path, tmp_path: Path):
    FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", str(tmp_path / "out.mkv")],
        ffmpeg_log_file=os.devnull,
        delete_log_on_success=True,
    ).run()
    assert os.path.exists(os.devnull)


def test_missing_tqdm(monkeypatch, input_file: Path, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "tqdm", None)
    with pytest.raises(FfmpegCommandError, match=r"better-ffmpeg-progress\[tqdm\]"):
        FfmpegProcess(["ffmpeg", "-i", str(input_file), str(tmp_path / "o.mkv")], use_tqdm=True)


@pytest.mark.skipif(sys.platform == "win32", reason="Standard output is not supported on Windows")
def test_output_to_stdout(input_file: Path, tmp_path: Path, capfdbinary):
    FfmpegProcess(
        ["ffmpeg", "-i", str(input_file), "-c:v", "ffv1", "-f", "matroska", "-"],
        ffmpeg_log_file=tmp_path / "log.txt",
    ).run()
    captured = capfdbinary.readouterr()
    # Standard output carries only the Matroska file, which starts with the EBML magic number.
    assert captured.out.startswith(b"\x1a\x45\xdf\xa3")
    assert b"out_time_us" not in captured.out
    # The progress bar is written to standard error instead.
    assert b"Processed" in captured.err


def test_ffmpeg_does_not_read_python_stdin(tmp_path: Path):
    script = (
        "import sys\n"
        "from better_ffmpeg_progress import FfmpegProcess\n"
        "FfmpegProcess(['ffmpeg', '-re', '-f', 'lavfi', '-i', 'testsrc2=duration=1:size=32x32',"
        " '-f', 'null', '-'], duration_override=1, ffmpeg_log_file=sys.argv[1]).run()\n"
        "sys.stderr.buffer.write(sys.stdin.buffer.read())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "log.txt")],
        input=b"data meant for Python\n",
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stderr.endswith(b"data meant for Python\n")


@pytest.mark.parametrize("use_tqdm", [False, True])
@pytest.mark.parametrize("duration_override", [None, 1])
def test_non_utf8_stdout(tmp_path: Path, use_tqdm: bool, duration_override):
    # e.g. standard output redirected on Windows, whose encoding is usually cp1252.
    script = (
        "import sys\n"
        "from better_ffmpeg_progress import FfmpegProcess\n"
        "FfmpegProcess(['ffmpeg', '-f', 'lavfi', '-i', 'testsrc2=duration=1:size=32x32',"
        " '-f', 'null', '-'], ffmpeg_log_file=sys.argv[1], use_tqdm=sys.argv[2] == 'True',"
        " duration_override=None if sys.argv[3] == 'None' else 1).run()\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(tmp_path / "log.txt"),
            str(use_tqdm),
            str(duration_override),
        ],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"OK Processed" in result.stdout + result.stderr
