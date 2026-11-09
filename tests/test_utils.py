import math
import os
import shutil
import sys
from pathlib import Path

import pytest

from better_ffmpeg_progress.utils import (
    build_failure_message,
    estimate_final_size_mb,
    find_ffprobe,
    get_expected_output_duration,
    get_input_format,
    get_inputs,
    get_media_duration,
    get_output_format,
    is_lavfi_input,
    is_local_file_input,
    is_null_device,
    parse_ffmpeg_time,
    parse_frame_rate,
    probe_media,
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
        (["-stream_loop", "2", "-i", "in.mp4", "out.mp4"], 300.0),
        (["-stream_loop", "-1", "-i", "in.mp4", "out.mp4"], None),
        (["-stream_loop", "-1", "-i", "in.mp4", "-t", "250", "out.mp4"], 250.0),
        (["-stream_loop", "-1", "-t", "250", "-i", "in.mp4", "out.mp4"], 250.0),
        (["-loop", "1", "-i", "in.png", "out.mp4"], None),
        (["-loop", "0", "-i", "in.png", "out.mp4"], 100.0),
        # 25 frames at the input's frame rate of 10 fps, or at the output's -r.
        (["-i", "in.mp4", "-frames:v", "25", "out.mp4"], 2.5),
        (["-i", "in.mp4", "-vframes", "25", "-r", "25", "out.mp4"], 1.0),
        (["-i", "in.mp4", "-frames:v", "5000", "out.mp4"], 100.0),
    ],
)
def test_get_expected_output_duration(args, expected):
    command = ["ffmpeg"] + (args or ["-i", "in.mp4", "out.mp4"])
    result = get_expected_output_duration(command, 100.0, frame_rate=10.0)
    assert result == (pytest.approx(expected) if expected is not None else None)


@pytest.mark.parametrize(
    "args, durations, expected",
    [
        # Without -shortest, the first input's duration is used.
        (["-i", "a.mp4", "-i", "b.mp4", "out.mp4"], [100.0, 40.0], 100.0),
        (["-i", "a.mp4", "-i", "b.mp4", "-shortest", "out.mp4"], [100.0, 40.0], 40.0),
        # A looped image with an audio track, the usual way to make a video from a song.
        (["-loop", "1", "-i", "a.png", "-i", "b.mp3", "-shortest", "o.mp4"], [0.04, 40.0], 40.0),
        # Each input's own options apply to it.
        (["-i", "a.mp4", "-ss", "30", "-i", "b.mp4", "-shortest", "o.mp4"], [100.0, 40.0], 10.0),
        # An input whose duration is unknown, e.g. a lavfi source, is ignored.
        (["-f", "lavfi", "-i", "color", "-i", "b.mp3", "-shortest", "o.mp4"], [None, 40.0], 40.0),
        (["-f", "lavfi", "-i", "color", "-i", "b.mp3", "o.mp4"], [None, 40.0], None),
    ],
)
def test_get_expected_output_duration_multiple_inputs(args, durations, expected):
    result = get_expected_output_duration(["ffmpeg", *args], durations[0], durations[1:])
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_get_inputs():
    command = ["ffmpeg", "-y", "-ss", "5", "-i", "a.mp4", "-f", "lavfi", "-i", "color", "out.mp4"]
    assert get_inputs(command) == [(["-y", "-ss", "5"], "a.mp4"), (["-f", "lavfi"], "color")]


@pytest.mark.parametrize(
    "value, expected",
    [("30", 30.0), ("29.97", 29.97), ("30000/1001", 30000 / 1001), ("0/0", None), ("ntsc", None)],
)
def test_parse_frame_rate(value, expected):
    assert parse_frame_rate(value) == (pytest.approx(expected) if expected else None)


def test_is_null_device():
    assert is_null_device(os.devnull)
    assert not is_null_device("out.mp4")


def _progress_block(**fields: str) -> list[bytes]:
    return [f"{key}={value}\n".encode() for key, value in fields.items()] + [
        b"progress=continue\n"
    ]


def test_read_progress():
    lines = [
        *_progress_block(frame="0", fps="0.00", bitrate="N/A", total_size="N/A", speed="N/A"),
        *_progress_block(frame="10", total_size="N/A", out_time_us="N/A"),
        *_progress_block(frame="15", total_size="0", out_time_us="500000"),
        *_progress_block(
            frame="45",
            fps="29.97",
            bitrate="1234.5kbits/s",
            total_size="1048576",
            out_time_us="1500000",
            speed="1.5x",
        ),
        *_progress_block(total_size="2097152", out_time_us="5000000"),
    ]
    reports = list(read_progress(lines, 2.0))
    assert [(p.secs, p.size_mb) for p in reports] == [
        (0.0, 0.0),
        (0.0, 0.0),
        (0.5, 0.0),
        (1.5, 1.0),
        (2.0, 2.0),
    ]
    assert reports[0].speed is None and reports[0].bitrate_kbps is None
    assert reports[3].speed == 1.5
    assert reports[3].fps == pytest.approx(29.97)
    assert reports[3].frame == 45
    assert reports[3].bitrate_kbps == 1234.5
    assert reports[3].percentage == pytest.approx(75.0)
    assert reports[3].duration_secs == 2.0
    # Fields are not carried over from the previous block.
    assert reports[4].frame is None

    # Without a duration, the seconds are not capped and there is no percentage. Negative
    # times are clamped to 0.
    reports = list(read_progress(_progress_block(out_time_us="-100") + lines, None))
    assert [p.secs for p in reports] == [0.0, 0.0, 0.0, 0.5, 1.5, 5.0]
    assert reports[-1].percentage is None


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
    output = '{"streams": [{"codec_type": "video", "avg_frame_rate": "25/1"}],'
    output += ' "format": {"duration": "12.5"}}'
    ffprobe = _make_executable(tmp_path / "ffprobe", f"echo '{output}'")
    assert get_media_duration("in.mp4", ffprobe=str(ffprobe)) == 12.5
    assert probe_media("in.mp4", ffprobe=str(ffprobe)).frame_rate == 25.0

    # Invalid output is treated as an unknown duration.
    bad_ffprobe = _make_executable(tmp_path / "bad_ffprobe", "echo 'N/A'")
    assert get_media_duration("in.mp4", ffprobe=str(bad_ffprobe)) is None

    slow_ffprobe = _make_executable(tmp_path / "slow_ffprobe", "exec sleep 10")
    assert get_media_duration("in.mp4", ffprobe=str(slow_ffprobe), timeout=0.2) is None
    assert "did not finish within 0.2 seconds" in caplog.text

    assert get_media_duration("in.mp4", ffprobe=os.fspath(tmp_path / "missing")) is None
    assert "FFprobe not found" in caplog.text


@pytest.mark.skipif(sys.platform == "win32", reason="Uses shell scripts")
def test_input_options_are_passed_to_ffprobe(tmp_path: Path):
    args_file = tmp_path / "args.txt"
    ffprobe = _make_executable(tmp_path / "ffprobe", f'echo "$@" > "{args_file}"; echo "{{}}"')
    probe_media("img%03d.png", ["-y", "-framerate", "5", "-hwaccel", "cuda"], str(ffprobe))
    args = args_file.read_text(encoding="utf-8").split()
    assert args[args.index("-framerate") + 1] == "5"
    # Options that FFprobe does not understand are not passed.
    assert "-y" not in args and "-hwaccel" not in args

    # FFprobe is not run for capture devices.
    args_file.unlink()
    assert probe_media("/dev/video0", ["-f", "v4l2"], str(ffprobe)).duration is None
    assert not args_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Uses shell scripts")
def test_concat_list_duration(tmp_path: Path):
    # FFprobe reports no duration for the list itself, and 10 seconds for each file.
    ffprobe = _make_executable(
        tmp_path / "ffprobe",
        'for arg; do last="$arg"; done\n'
        'case "$last" in *.txt) echo "{}" ;; *) echo \'{"format": {"duration": "10"}}\' ;; esac',
    )
    list_file = tmp_path / "list.txt"
    list_file.write_text(
        "ffconcat version 1.0\n"
        "# A comment\n"
        "file 'part 1.mp4'\n"
        "file part2.mp4\n"
        "inpoint 4\n"
        "file '/abs/part3.mp4'\n"
        "outpoint 00:00:03\n"
        "file part4.mp4\n"
        "duration 2.5\n",
        encoding="utf-8",
    )
    duration = get_media_duration(
        str(list_file), ffprobe=str(ffprobe), input_options=["-f", "concat", "-safe", "0"]
    )
    assert duration == pytest.approx(10 + 6 + 3 + 2.5)

    # Without "-f concat", the list is not read.
    assert get_media_duration(str(list_file), ffprobe=str(ffprobe)) is None


def test_concat_list_with_missing_file(tmp_path: Path):
    if not shutil.which("ffprobe"):
        pytest.skip("FFprobe is required")
    list_file = tmp_path / "list.txt"
    list_file.write_text("file 'missing.mp4'\n", encoding="utf-8")
    assert get_media_duration(str(list_file), input_options=["-f", "concat"]) is None


def test_infinite_duration_is_unknown():
    command = ["ffmpeg", "-stream_loop", "-1", "-i", "in.mp4", "out.mp4"]
    assert get_expected_output_duration(command, math.inf) is None
