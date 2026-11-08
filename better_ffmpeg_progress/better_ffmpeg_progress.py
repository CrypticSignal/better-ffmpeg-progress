from __future__ import annotations

import contextlib
import math
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, TextIO

from .enums import FfmpegLogLevel
from .exceptions import (
    FfmpegCommandError,
    FfmpegProcessError,
    FfmpegProcessInterruptedError,
    FfmpegProcessUserCancelledError,
)
from .progress_bars import make_display
from .terminate_process import terminate_ffmpeg_process
from .utils import (
    build_failure_message,
    find_ffprobe,
    get_expected_output_duration,
    get_media_duration,
    is_lavfi_input,
    is_local_file_input,
    is_stdin_input,
    read_progress,
    truncate_filename,
    validate_ffmpeg_command,
    writes_to_stdout,
)

_MAX_FILENAME_LENGTH = 60

ProgressCallback = Callable[[float, "float | None", float], None]


def _safe_filename(name: str) -> str:
    """Replaces characters that are not valid in filenames on every OS."""
    return re.sub(r"[^\w.,-]", "_", name)


def _parse_log_level(ffmpeg_log_level: FfmpegLogLevel | str | None) -> FfmpegLogLevel:
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


def _default_log_file(command: list[str], input_flag_pos: int) -> Path:
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
        command: list[str],
        ffmpeg_log_level: FfmpegLogLevel | str | None = None,
        ffmpeg_log_file: str | os.PathLike[str] | IO[Any] | None = None,
        print_detected_duration: bool = False,
        duration_override: float | None = None,
        overwrite: bool | None = None,
        use_tqdm: bool = False,
        quiet: bool = False,
        progress_callback: ProgressCallback | None = None,
        delete_log_on_success: bool = False,
    ):
        """
        Create an FFmpeg process with progress reporting. Nothing is run until run() is called.

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
                Use tqdm instead of Rich for the progress bar. Requires tqdm, which can be
                installed with `pip install better-ffmpeg-progress[tqdm]`.
            quiet:
                Do not show a progress bar or status messages.
            progress_callback:
                A function called each time FFmpeg reports its progress, with the number of
                seconds processed, the expected output duration in seconds (or None if it is
                unknown) and the current output size in MB. If it raises an exception, FFmpeg
                is stopped and the exception is propagated.
            delete_log_on_success:
                Delete the log file if FFmpeg succeeds. Only applies when the log is written to
                a regular file given by path (or the default log file).
        """
        validate_ffmpeg_command(command)
        self._log_level = _parse_log_level(ffmpeg_log_level)
        if overwrite is not None and not isinstance(overwrite, bool):
            raise TypeError("overwrite must be True, False or None")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback must be callable or None")
        if use_tqdm:
            try:
                import tqdm  # noqa: F401
            except ImportError:
                raise FfmpegCommandError(
                    "use_tqdm=True requires tqdm. Install it with: "
                    "pip install better-ffmpeg-progress[tqdm]"
                ) from None

        self._writes_to_stdout = writes_to_stdout(command)
        if self._writes_to_stdout and os.name == "nt":
            raise FfmpegCommandError(
                "Writing the output to standard output is not supported on Windows."
            )

        self._command = list(command)
        input_flag_pos = command.index("-i")
        self._input_file = command[input_flag_pos + 1]
        self._input_filepath = Path(self._input_file)
        # Assumes the last argument is the output.
        self._output_filepath = Path(command[-1])

        self._ffmpeg_log_file: Path | IO[Any]
        if ffmpeg_log_file is None:
            self._ffmpeg_log_file = _default_log_file(command, input_flag_pos)
        elif isinstance(ffmpeg_log_file, (str, os.PathLike)):
            self._ffmpeg_log_file = Path(ffmpeg_log_file)
        else:
            self._ffmpeg_log_file = ffmpeg_log_file

        self._duration_override = (
            _parse_duration_override(duration_override) if duration_override is not None else None
        )
        self._print_detected_duration = print_detected_duration
        self._overwrite = overwrite
        self._quiet = quiet
        self._progress_callback = progress_callback
        self._delete_log_on_success = delete_log_on_success
        self._duration_secs: float | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self.use_tqdm: bool = use_tqdm

    @property
    def _message_stream(self) -> TextIO:
        """
        Where the progress bar and messages are written. If FFmpeg writes the output to standard
        output, they are written to standard error, so they do not get mixed with the output.
        """
        return sys.stderr if self._writes_to_stdout else sys.stdout

    def _get_output_duration(self) -> float | None:
        """Returns the expected duration of the output in seconds, or None if it is unknown."""
        if self._duration_override is not None:
            input_duration_secs: float | None = self._duration_override
        elif is_stdin_input(self._input_file):
            # Running FFprobe on standard input would consume data that is meant for FFmpeg.
            input_duration_secs = None
        else:
            input_duration_secs = get_media_duration(
                self._input_file, ffprobe=find_ffprobe(self._command[0])
            )

        # Account for trimming (-ss, -sseof, -t, -to) so the progress bar reflects the
        # duration of the output rather than the whole input.
        duration_secs = (
            get_expected_output_duration(self._command, input_duration_secs)
            if input_duration_secs is not None
            else None
        )

        if self._print_detected_duration or (
            self._duration_override is not None and not self._quiet
        ):
            stream = self._message_stream
            if input_duration_secs is None:
                print(
                    "Could not detect duration. Progress bar may not show time remaining.",
                    file=stream,
                )
            else:
                label = (
                    "Using duration override"
                    if self._duration_override is not None
                    else "Detected duration"
                )
                print(f"{label}: {input_duration_secs:.2f} seconds", file=stream)
                if duration_secs != input_duration_secs:
                    print(
                        f"Expected output duration after trimming: {duration_secs:.2f} seconds",
                        file=stream,
                    )

        return duration_secs

    def _should_overwrite(self) -> bool:
        """
        Returns True if "-y" must be added to the command because the output file exists and may be
        overwritten. Raises an FfmpegProcessError if it must not be overwritten.
        """
        user_args = self._command[1:]
        if "-y" in user_args or self._writes_to_stdout or not self._output_filepath.exists():
            return False
        if "-n" in user_args or self._overwrite is False:
            raise FfmpegCommandError(
                f"Output file {self._output_filepath} already exists and overwriting is disabled."
            )
        if self._overwrite is None:
            if is_stdin_input(self._input_file):
                # Prompting would read from standard input, which carries FFmpeg's input.
                raise FfmpegCommandError(
                    f"Output file {self._output_filepath} already exists. Pass "
                    "overwrite=True or add -y to the command to overwrite it."
                )
            self._ask_to_overwrite()
        return True

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

    def _build_command(self, progress_url: str, overwrite: bool) -> list[str]:
        return [
            self._command[0],
            *(["-y"] if overwrite else []),
            "-hide_banner",
            "-loglevel",
            self._log_level.value,
            "-progress",
            progress_url,
            "-nostats",
            *self._command[1:],
        ]

    def run(self, print_command: bool = False) -> None:
        """
        Runs FFmpeg and shows its progress until it exits.

        Raises:
            FfmpegProcessError: If FFmpeg fails, or cannot be started. Its returncode and
                log_file attributes are set when available.
            FfmpegProcessInterruptedError: If Ctrl+C is pressed. FFmpeg is stopped first.
        """
        overwrite = self._should_overwrite()
        self._duration_secs = self._get_output_duration()

        if isinstance(self._ffmpeg_log_file, Path):
            log_file: Any = open(self._ffmpeg_log_file, "w", encoding="utf-8")
        else:
            log_file = contextlib.nullcontext(self._ffmpeg_log_file)

        # FFmpeg's progress is read from a pipe. On POSIX, a separate pipe is used, so FFmpeg's
        # standard output stays free for the output (e.g. "-f mpegts -"). On Windows, where
        # passing extra file descriptors is not supported, standard output is used.
        read_fd: int | None = None
        write_fd: int | None = None
        popen_kwargs: dict[str, Any]
        if os.name == "nt":
            progress_url = "pipe:1"
            # Run FFmpeg in its own process group, so that pressing Ctrl+C does not send the
            # signal to FFmpeg directly.
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            }
        else:
            read_fd, write_fd = os.pipe()
            progress_url = f"pipe:{write_fd}"
            # Run FFmpeg in its own session, so that pressing Ctrl+C does not send the signal to
            # FFmpeg directly, and terminating its process group does not terminate Python.
            popen_kwargs = {"pass_fds": (write_fd,), "start_new_session": True}

        # FFmpeg reads commands such as "q" from standard input. Unless standard input carries
        # FFmpeg's input, give it a pipe instead, so it does not consume data meant for this
        # program or change the terminal's settings. Writing "q" to the pipe stops FFmpeg
        # cleanly (see terminate_ffmpeg_process).
        stdin = None if is_stdin_input(self._input_file) else subprocess.PIPE

        ffmpeg_command = self._build_command(progress_url, overwrite)
        if print_command:
            print(f"Executing: {shlex.join(ffmpeg_command)}", file=self._message_stream)

        try:
            # FFmpeg keeps its own handle to the log file, so it can be closed here.
            with log_file as stderr:
                self._process = subprocess.Popen(
                    ffmpeg_command, stdin=stdin, stderr=stderr, **popen_kwargs
                )
        except Exception as e:
            if read_fd is not None:
                os.close(read_fd)
            raise FfmpegProcessError(
                f"Error starting FFmpeg process: {e}", log_file=self._ffmpeg_log_file
            ) from e
        finally:
            # FFmpeg has its own copy of the write end. Closing this one means reading the pipe
            # ends when FFmpeg exits.
            if write_fd is not None:
                os.close(write_fd)

        process = self._process
        if read_fd is not None:
            progress_stream: IO[bytes] = os.fdopen(read_fd, "rb")
        else:
            assert process.stdout is not None
            progress_stream = process.stdout

        filename = truncate_filename(self._input_filepath.name, _MAX_FILENAME_LENGTH)
        display = make_display(
            filename, self._duration_secs, self._message_stream, self._quiet, self.use_tqdm
        )

        try:
            # The progress output must always be read, even if it is not displayed: once the
            # pipe's buffer is full, FFmpeg blocks and never exits.
            with progress_stream, display:
                size_mb = 0.0
                for secs, size_mb in read_progress(progress_stream, self._duration_secs):
                    display.update(secs, size_mb)
                    if self._progress_callback is not None:
                        self._progress_callback(secs, self._duration_secs, size_mb)
                returncode = process.wait()
                if returncode == 0:
                    display.complete(size_mb)
        except KeyboardInterrupt as e:
            terminate_ffmpeg_process(process)
            raise FfmpegProcessInterruptedError(
                "[KeyboardInterrupt] FFmpeg process cancelled.",
                returncode=process.returncode,
                log_file=self._ffmpeg_log_file,
            ) from e
        except BaseException:
            # e.g. an exception raised by progress_callback.
            terminate_ffmpeg_process(process)
            raise
        finally:
            if process.stdin is not None:
                with contextlib.suppress(OSError):
                    process.stdin.close()

        if returncode != 0:
            raise FfmpegProcessError(
                build_failure_message(self._ffmpeg_log_file),
                returncode=returncode,
                log_file=self._ffmpeg_log_file,
            )

        if (
            self._delete_log_on_success
            and isinstance(self._ffmpeg_log_file, Path)
            # Never delete e.g. os.devnull.
            and self._ffmpeg_log_file.is_file()
        ):
            with contextlib.suppress(OSError):
                self._ffmpeg_log_file.unlink()
