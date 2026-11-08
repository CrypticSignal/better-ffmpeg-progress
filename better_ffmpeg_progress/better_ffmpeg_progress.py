import contextlib
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import IO, Any, List, Optional, Union

from .enums import FfmpegLogLevel
from .exceptions import (
    FfmpegCommandError,
    FfmpegProcessError,
    FfmpegProcessInterruptedError,
    FfmpegProcessUserCancelledError,
)
from .progress_bars import show_rich_progress, show_tqdm_progress
from .terminate_process import terminate_ffmpeg_process
from .utils import (
    build_failure_message,
    get_expected_output_duration,
    get_media_duration,
    is_lavfi_input,
    is_local_file_input,
    is_stdin_input,
    truncate_filename,
    validate_ffmpeg_command,
)

_MAX_FILENAME_LENGTH = 60


def _safe_filename(name: str) -> str:
    """Replaces characters that are not valid in filenames on every OS."""
    return re.sub(r"[^\w.,-]", "_", name)


def _parse_log_level(ffmpeg_log_level: Optional[Union[FfmpegLogLevel, str]]) -> FfmpegLogLevel:
    if ffmpeg_log_level is None:
        return FfmpegLogLevel.VERBOSE
    if isinstance(ffmpeg_log_level, FfmpegLogLevel):
        return ffmpeg_log_level
    if not isinstance(ffmpeg_log_level, str):
        raise TypeError(
            "ffmpeg_log_level must be an FfmpegLogLevel, a string or None, not "
            f"{type(ffmpeg_log_level).__name__}"
        )
    try:
        return FfmpegLogLevel(ffmpeg_log_level.lower())
    except ValueError:
        valid_levels = [level.value for level in FfmpegLogLevel]
        raise FfmpegCommandError(
            f"Invalid ffmpeg_log_level string: '{ffmpeg_log_level}'. "
            f"Must be one of {valid_levels} (case-insensitive)."
        ) from None


def _parse_duration_override(duration_override: Any) -> float:
    if isinstance(duration_override, bool):
        raise TypeError("duration_override must be a number of seconds, not bool")
    try:
        duration = float(duration_override)
    except (TypeError, ValueError) as e:
        raise TypeError("duration_override must be a number of seconds or None") from e
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration_override must be a finite number greater than 0")
    return duration


def _default_log_file(command: List[str], input_flag_pos: int) -> Path:
    """Returns the default log file path, which is named after the input."""
    input_file = command[input_flag_pos + 1]

    if is_lavfi_input(command, input_flag_pos):
        # A filtergraph such as "testsrc2=size=1920x1080" can contain characters that are not
        # valid in filenames (e.g. ":" on Windows), so name the log after the source instead.
        source_name = _safe_filename(input_file.split("=", 1)[0])
        return Path(f"lavfi_{source_name}_ffmpeg_log.txt")
    if input_file == "-":
        return Path("stdin_ffmpeg_log.txt")
    if is_local_file_input(command, input_flag_pos):
        return Path(f"{Path(input_file).name}_ffmpeg_log.txt")
    # URLs and other protocols (e.g. "pipe:0") can contain characters that are not valid in
    # filenames, such as ":" or "?".
    name = Path(input_file).name or input_file
    return Path(f"{_safe_filename(name)}_ffmpeg_log.txt")


class FfmpegProcess:
    def __init__(
        self,
        command: List[str],
        ffmpeg_log_level: Optional[Union[FfmpegLogLevel, str]] = None,
        ffmpeg_log_file: Optional[Union[str, os.PathLike, IO[Any]]] = None,
        print_detected_duration: bool = False,
        duration_override: Optional[float] = None,
        overwrite: Optional[bool] = None,
        use_tqdm: bool = False,
    ):
        """
        Create an FFmpeg process with progress reporting.

        Args:
            command:
                FFmpeg command as a list of arguments.
            ffmpeg_log_level:
                FFmpeg log level enum or case-insensitive string.
            ffmpeg_log_file:
                File path or file object (with a file descriptor, e.g. one returned by open())
                to which FFmpeg's stderr is written.
            print_detected_duration:
                Print the duration used for progress calculation.
            duration_override:
                Specify input file duration in seconds to use for progress calculation, instead
                of trying to detect this automatically with FFprobe. This is useful for partial,
                damaged, streamed, or synthetic inputs whose duration cannot be detected
                correctly.
            overwrite:
                What to do if the output file already exists. True overwrites it, False raises
                FfmpegCommandError, and None (the default) asks the user. Ignored if the command
                contains -y or -n.
            use_tqdm:
                Use tqdm instead of Rich for the progress bar.
        """
        validate_ffmpeg_command(command)
        log_level = _parse_log_level(ffmpeg_log_level)
        if overwrite is not None and not isinstance(overwrite, bool):
            raise TypeError("overwrite must be True, False or None")

        input_flag_pos = command.index("-i")
        input_file = command[input_flag_pos + 1]
        self._input_filepath = Path(input_file)
        # Assumes the last argument is the output.
        self._output_filepath = Path(command[-1])

        if ffmpeg_log_file is None:
            self._ffmpeg_log_file = _default_log_file(command, input_flag_pos)
        elif isinstance(ffmpeg_log_file, (str, os.PathLike)):
            self._ffmpeg_log_file = Path(ffmpeg_log_file)
        else:
            self._ffmpeg_log_file = ffmpeg_log_file

        if duration_override is not None:
            input_duration_secs = _parse_duration_override(duration_override)
        elif is_stdin_input(input_file):
            # Running FFprobe on standard input would consume data that is meant for FFmpeg.
            input_duration_secs = None
        else:
            input_duration_secs = get_media_duration(input_file)

        # Account for trimming (-ss, -sseof, -t, -to) so the progress bar reflects the
        # duration of the output rather than the whole input.
        self._duration_secs = (
            get_expected_output_duration(command, input_duration_secs)
            if input_duration_secs is not None
            else None
        )

        if duration_override is not None or print_detected_duration:
            if input_duration_secs is None:
                print("Could not detect duration. Progress bar may not show time remaining.")
            else:
                label = (
                    "Using duration override"
                    if duration_override is not None
                    else "Detected duration"
                )
                print(f"{label}: {input_duration_secs:.2f} seconds")
                if self._duration_secs != input_duration_secs:
                    print(
                        "Expected output duration after trimming: "
                        f"{self._duration_secs:.2f} seconds"
                    )

        self._ffmpeg_command = [
            command[0],
            "-hide_banner",
            "-loglevel",
            log_level.value,
            "-progress",
            "pipe:1",
            "-nostats",
            *command[1:],
        ]

        user_args = command[1:]
        if "-y" not in user_args and self._output_filepath.exists():
            if "-n" in user_args or overwrite is False:
                raise FfmpegCommandError(
                    f"Output file {self._output_filepath} already exists and overwriting is "
                    "disabled."
                )
            if overwrite is None:
                if is_stdin_input(input_file):
                    # Prompting would read from standard input, which carries FFmpeg's input.
                    raise FfmpegCommandError(
                        f"Output file {self._output_filepath} already exists. Pass "
                        "overwrite=True or add -y to the command to overwrite it."
                    )
                self._ask_to_overwrite()
            self._ffmpeg_command.insert(1, "-y")

        self._process: Optional[subprocess.Popen] = None
        self.use_tqdm: bool = use_tqdm

    def _ask_to_overwrite(self) -> None:
        """Raises an FfmpegProcessError unless the user agrees to overwrite the output file."""
        try:
            answer = input(
                f"Output file {self._output_filepath} already exists. Overwrite? [y/N]: "
            )
        except KeyboardInterrupt as e:
            raise FfmpegProcessInterruptedError(
                "[KeyboardInterrupt] FFmpeg process cancelled during overwrite prompt."
            ) from e
        except EOFError as e:
            raise FfmpegProcessInterruptedError(
                "Input error (EOF) during overwrite prompt. FFmpeg process cancelled."
            ) from e

        if answer.strip().lower() != "y":
            raise FfmpegProcessUserCancelledError(
                "FFmpeg process cancelled. Output file exists and overwrite declined."
            )

    def run(self, print_command: bool = False) -> None:
        if print_command:
            print(f"Executing: {shlex.join(self._ffmpeg_command)}")

        # Run FFmpeg in its own process group, so that pressing Ctrl+C does not send the signal
        # to FFmpeg directly, and terminating the group does not terminate this Python process.
        if os.name == "nt":
            new_process_group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            new_process_group = {"start_new_session": True}

        if isinstance(self._ffmpeg_log_file, Path):
            log_file = open(self._ffmpeg_log_file, "w", encoding="utf-8")
        else:
            log_file = contextlib.nullcontext(self._ffmpeg_log_file)

        try:
            # FFmpeg keeps its own handle to the log file, so it can be closed here.
            with log_file as stderr:
                self._process = subprocess.Popen(
                    self._ffmpeg_command,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    **new_process_group,
                )
        except Exception as e:
            raise FfmpegProcessError(f"Error starting FFmpeg process: {e}") from e

        filename = truncate_filename(self._input_filepath.name, _MAX_FILENAME_LENGTH)
        try:
            with self._process.stdout:
                if not self._duration_secs:
                    print(f"Processing '{filename}'...")
                    # FFmpeg's progress output must be read even though it is not displayed:
                    # once the pipe's buffer is full, FFmpeg blocks and never exits.
                    for _ in self._process.stdout:
                        pass
                elif self.use_tqdm:
                    show_tqdm_progress(self._process, filename, self._duration_secs)
                else:
                    show_rich_progress(self._process, filename, self._duration_secs)
                returncode = self._process.wait()
        except KeyboardInterrupt as e:
            terminate_ffmpeg_process(self._process)
            raise FfmpegProcessInterruptedError(
                "[KeyboardInterrupt] FFmpeg process cancelled."
            ) from e

        if returncode != 0:
            raise FfmpegProcessError(build_failure_message(self._ffmpeg_log_file))
        if not self._duration_secs:
            print(f"✓ Processed '{filename}'")
