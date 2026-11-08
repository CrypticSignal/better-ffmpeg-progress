import os
import sys
from pathlib import Path

import pytest

from better_ffmpeg_progress.utils import (
    build_failure_message,
    estimate_final_size_mb,
    find_ffprobe,
    get_expected_output_duration,
    get_input_format,
    get_media_duration,
    get_output_format,
    is_lavfi_input,
    is_local_file_input,
    parse_ffmpeg_time,
    read_progress,
    truncate_filename,
    writes_to_stdout,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("90", 90.0),
        ("1.5", 1.5),
        (".5", 0.5),
        ("500ms", 0.5),
        ("250000us", 0.25),
        ("2s", 2.0),
        ("01:30", 90.0),
        ("00:01:30.5", 90.5),
        ("-5", -5.0),
        ("-00:00:10", -10.0),
        (" 10 ", 10.0),
        ("abc", None),
        ("1:2:3:4", None),
    ],
)
def test_parse_ffmpeg_time(value, expected):
    assert parse_ffmpeg_time(value) == expected


@pytest.mark.parametrize(
    "args, expected",
    [
        ([], 100.0),
        (["-ss", "10", "-i", "in.mp4", "out.mp4"], 90.0),
        (["-i", "in.mp4", "-ss", "10", "out.mp4"], 90.0),
        (["-i", "in.mp4", "-t", "30", "out.mp4"], 30.0),
        (["-i", "in.mp4", "-to", "40", "out.mp4"], 40.0),
        (["-ss", "10", "-to", "40", "-i", "in.mp4", "out.mp4"], 30.0),
        (["-ss", "10", "-t", "20", "-to", "80", "-i", "in.mp4", "out.mp4"], 20.0),
        (["-sseof", "-15", "-i", "in.mp4", "out.mp4"], 15.0),
        (["-ss", "10", "-i", "in.mp4", "-t", "200", "out.mp4"], 90.0),
        (["-ss", "10", "-copyts", "-i", "in.mp4", "out.mp4"], 100.0),
        # A trim that leaves nothing falls back to the input duration.
        (["-ss", "200", "-i", "in.mp4", "out.mp4"], 100.0),
    ],
)
def test_get_expected_output_duration(args, expected):
    command = ["ffmpeg"] + (args or ["-i", "in.mp4", "out.mp4"])
    assert get_expected_output_duration(command, 100.0) == pytest.approx(expected)


def test_read_progress():
    lines = [
        b"frame=10\n",
        b"total_size=N/A\n",
        b"out_time_us=N/A\n",
        b"out_time_us=500000\n",
        b"total_size=1048576\n",
        b"out_time_us=1500000\n",
        b"total_size=2097152\n",
        b"out_time_us=5000000\n",
    ]
    assert list(read_progress(lines, 2.0)) == [(0.5, 0.0), (1.5, 1.0), (2.0, 2.0)]
    # Without a duration, the seconds are not capped. Negative times are clamped to 0.
    assert list(read_progress([b"out_time_us=-100\n"] + lines, None)) == [
        (0.0, 0.0),
        (0.5, 0.0),
        (1.5, 1.0),
        (5.0, 2.0),
    ]


def test_truncate_filename():
    assert truncate_filename("short.mp4", 60) == "short.mp4"
    truncated = truncate_filename("a" * 100 + ".mp4", 20)
    assert truncated == "a" * 13 + "....mp4"
    assert len(truncated) == 20
    assert len(truncate_filename("a" * 10 + "." + "b" * 30, 20)) == 20


def test_estimate_final_size_mb():
    assert estimate_final_size_mb(10.0, 0.5, 100.0) is None
    assert estimate_final_size_mb(0.0, 50.0, 100.0) is None
    assert estimate_final_size_mb(10.0, 50.0, 100.0) == pytest.approx(20.0)


@pytest.mark.parametrize(
    "args, expected_format, expected_local",
    [
        (["-i", "in.mp4"], None, True),
        (["-i", "C:\\videos\\in.mp4"], None, True),
        (["-f", "lavfi", "-i", "testsrc2"], "lavfi", False),
        (["-f", "image2", "-pattern_type", "glob", "-i", "*.png"], "image2", False),
        (["-i", "-"], None, False),
        (["-i", "pipe:0"], None, False),
        (["-i", "https://example.com/in.mp4"], None, False),
        (["-i", "rtsp://example.com/stream"], None, False),
    ],
)
def test_input_classification(args, expected_format, expected_local):
    command = ["ffmpeg"] + args + ["out.mp4"]
    input_flag_pos = command.index("-i")
    assert get_input_format(command, input_flag_pos) == expected_format
    assert is_lavfi_input(command, input_flag_pos) == (expected_format == "lavfi")
    assert is_local_file_input(command, input_flag_pos) == expected_local


def test_build_failure_message(tmp_path: Path):
    log_file = tmp_path / "log.txt"
    log_file.write_text("".join(f"line {i}\n" for i in range(10)), encoding="utf-8")
    message = build_failure_message(log_file, max_lines=3)
    assert message.endswith("line 7\nline 8\nline 9")

    assert build_failure_message(tmp_path / "missing.txt").endswith("for details.")
    assert build_failure_message(object()).endswith("for details.")


@pytest.mark.parametrize(
    "args, expected_format, expected_stdout",
    [
        (["-i", "in.mp4", "out.mp4"], None, False),
        (["-i", "in.mp4", "-f", "null", "-"], "null", False),
        (["-f", "mpegts", "-i", "in.ts", "-f", "matroska", "-"], "matroska", True),
        (["-i", "in.mp4", "-f", "mpegts", "pipe:1"], "mpegts", True),
        (["-i", "in.mp4", "-f", "mpegts", "pipe:"], "mpegts", True),
        (["-i", "in.mp4", "-f", "mpegts", "pipe:3"], "mpegts", False),
        (["-i", "-", "-f", "mpegts", "out.ts"], "mpegts", False),
    ],
)
def test_output_classification(args, expected_format, expected_stdout):
    command = ["ffmpeg"] + args
    assert get_output_format(command) == expected_format
    assert writes_to_stdout(command) == expected_stdout


def _make_executable(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="Uses shell scripts")
def test_find_ffprobe_prefers_sibling(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ffmpeg = _make_executable(bin_dir / "ffmpeg", "exit 0")
    ffprobe = _make_executable(bin_dir / "ffprobe", "exit 0")
    assert find_ffprobe(str(ffmpeg)) == str(ffprobe)

    # Without a sibling, the ffprobe in PATH is used.
    ffprobe.unlink()
    path_dir = tmp_path / "path"
    path_dir.mkdir()
    path_ffprobe = _make_executable(path_dir / "ffprobe", "exit 0")
    monkeypatch.setenv("PATH", str(path_dir))
    assert find_ffprobe(str(ffmpeg)) == str(path_ffprobe)

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert find_ffprobe(str(ffmpeg)) is None


@pytest.mark.skipif(sys.platform == "win32", reason="Uses shell scripts")
def test_get_media_duration(tmp_path: Path, caplog):
    ffprobe = _make_executable(tmp_path / "ffprobe", "echo 12.5")
    assert get_media_duration("in.mp4", ffprobe=str(ffprobe)) == 12.5

    slow_ffprobe = _make_executable(tmp_path / "slow_ffprobe", "exec sleep 10")
    assert get_media_duration("in.mp4", ffprobe=str(slow_ffprobe), timeout=0.2) is None
    assert "did not finish within 0.2 seconds" in caplog.text

    assert get_media_duration("in.mp4", ffprobe=os.fspath(tmp_path / "missing")) is None
    assert "FFprobe not found" in caplog.text
