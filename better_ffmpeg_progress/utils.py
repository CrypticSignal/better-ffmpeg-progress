import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
import requests  # Added for URL validation

from .exceptions import FfmpegCommandError

_FFMPEG_INPUT_FLAG = "-i"
_OUT_TIME_US_PREFIX = b"out_time_us="
_MULTIPLIER = 1e-6


def validate_ffmpeg_command(command: List[str]) -> None:
    """
    Validates the FFmpeg command.
    Raises FfmpegCommandError if validation fails.
    """
    if not command:
        raise FfmpegCommandError("FFmpeg command list cannot be empty.")

    ffmpeg_executable = command[0]
    if not shutil.which(ffmpeg_executable):
        err_msg = (
            f"'{ffmpeg_executable}' not found. "
            "Ensure it's in your system's PATH or provide the full path of the FFmpeg executable."
        )

        raise FfmpegCommandError(err_msg)

    if _FFMPEG_INPUT_FLAG not in command:
        raise FfmpegCommandError(
            f"FFmpeg command must include the input flag '{_FFMPEG_INPUT_FLAG}'."
        )

    try:
        input_flag_pos = command.index(_FFMPEG_INPUT_FLAG)
    except ValueError:
        raise FfmpegCommandError(
            f"Internal error: Input flag '{_FFMPEG_INPUT_FLAG}' not found after check."
        )

    input_file_idx = input_flag_pos + 1
    if input_file_idx >= len(command):
        raise FfmpegCommandError(
            f"No input file specified after '{_FFMPEG_INPUT_FLAG}'."
        )

    input_file = command[input_file_idx]
    if (
        input_file.startswith("-")
        and len(input_file) == 2
        and not input_file[1:].isdigit()
    ):
        raise FfmpegCommandError(
            f"Input file path '{input_file}' looks like an option flag. Please check your command."
        )

    # Validate input file/URL
    if input_file.startswith("http://") or input_file.startswith("https://"):
        try:
            response = requests.head(input_file, timeout=5, allow_redirects=True)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise FfmpegCommandError(
                f"Input URL not accessible: {input_file}. Error: {e}"
            )
    elif not Path(input_file).exists():
        raise FfmpegCommandError(f"Input file not found: {input_file}")

    if len(command) <= input_file_idx + 1:
        raise FfmpegCommandError(
            "No output file specified. The command seems to end after the input file path."
        )

    output_file_path_str = command[-1]
    if output_file_path_str == input_file:
        raise FfmpegCommandError(
            "Output file path cannot be the same as the input file path in this command structure."
        )


def get_media_duration(input_file: str) -> Optional[float]:
    """
    Retrieves the duration of a media file or URL using ffprobe.
    Returns duration in seconds, or None if it cannot be determined.
    Accepts input_file as a string to correctly handle URLs.
    """
    if not shutil.which("ffprobe"):
        print("Warning: ffprobe not found in PATH. Cannot determine media duration.")
        return None
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                "-i",
                input_file,
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return float(output)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        print(f"Warning: Could not determine duration for '{input_file}'.")
        return None


def check_shell_needed_for_command(command: List[str]) -> bool:
    """
    Checks if any part of the command contains shell operators,
    indicating that shell=True might be needed for subprocess.Popen.
    This is a basic check and might not cover all edge cases.
    """
    shell_operators = {"|", ">", "<", ">>", "&&", "||"}  # Basic set
    return any(op in item for item in command for op in shell_operators)


def parse_ffmpeg_progress_line(
    line: bytes, total_duration_secs: Optional[float]
) -> Optional[float]:
    """
    Parses a progress line from FFmpeg's stdout.
    Example line: b"out_time_us=12345678"
    Returns the current progress time in seconds, or None if parsing fails or line is not a progress line.
    Caps progress at total_duration_secs if provided.
    Assumes `line` has already been stripped of leading/trailing whitespace.
    """
    if line.startswith(_OUT_TIME_US_PREFIX):
        try:
            # Get the value after out_time_us=
            value_str = line[len(_OUT_TIME_US_PREFIX) :]

            if not value_str:
                return None

            current_time_us = int(value_str)
            current_time_secs = current_time_us * _MULTIPLIER

            if total_duration_secs is not None:
                return min(current_time_secs, total_duration_secs)
            return current_time_secs
        except (ValueError, IndexError):
            return None

    return None
