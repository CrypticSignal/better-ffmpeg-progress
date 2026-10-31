from pathlib import Path

import pytest

from better_ffmpeg_progress.utils import (
    build_failure_message,
    estimate_final_size_mb,
    get_expected_output_duration,
    get_input_format,
    is_lavfi_input,
    is_local_file_input,
    parse_ffmpeg_progress_line,
    parse_ffmpeg_time,
    parse_ffmpeg_total_size_line,
    truncate_filename,
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


def test_parse_ffmpeg_progress_line():
    assert parse_ffmpeg_progress_line(b"out_time_us=1500000", None) == pytest.approx(1.5)
    assert parse_ffmpeg_progress_line(b"out_time_us=1500000", 1.0) == 1.0
    assert parse_ffmpeg_progress_line(b"out_time_us=N/A", 10.0) is None
    assert parse_ffmpeg_progress_line(b"out_time_us=", 10.0) is None
    assert parse_ffmpeg_progress_line(b"frame=10", 10.0) is None


def test_parse_ffmpeg_total_size_line():
    assert parse_ffmpeg_total_size_line(b"total_size=1048576") == 1.0
    assert parse_ffmpeg_total_size_line(b"total_size=N/A") is None
    assert parse_ffmpeg_total_size_line(b"out_time_us=1") is None


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
