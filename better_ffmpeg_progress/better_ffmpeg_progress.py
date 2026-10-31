import math
import os
import re
import shlex
from pathlib import Path
import subprocess
from typing import List, Optional, Union

from .enums import FfmpegLogLevel
from .exceptions import (
    FfmpegProcessError,
    FfmpegCommandError,
    FfmpegProcessUserCancelledError,
    FfmpegProcessInterruptedError,
)
from .utils import (
    validate_ffmpeg_command,
    get_media_duration,
    get_expected_output_duration,
    is_lavfi_input,
    is_local_file_input,
    is_stdin_input,
)
from .terminate_process import terminate_ffmpeg_process
from .progress_bars import use_rich, use_tqdm

_FFMPEG_OVERWRITE_FLAG = "-y"
_FFMPEG_NO_OVERWRITE_FLAG = "-n"


def _safe_filename(name: str) -> str:
    """Replaces characters that are not valid in filenames on every OS."""
    return re.sub(r"[^\w.,-]", "_", name)


class FfmpegProcess:
    def _handle_overwrite_prompt(self) -> None:
        """
        Handles the logic for overwriting an existing output file.
        Modifies self._ffmpeg_command to include -y if overwrite is confirmed.
        Raises FfmpegProcessUserCancelledError or
        FfmpegProcessInterruptedError if not proceeding.
        """
        try:
            answer = (
                input(f"Output file {self._output_filepath} already exists. Overwrite? [y/N]: ")
                .strip()
                .lower()
            )
            if answer == "y":
                self._ffmpeg_command.insert(1, _FFMPEG_OVERWRITE_FLAG)
            else:
                raise FfmpegProcessUserCancelledError(
                    "FFmpeg process cancelled. Output file exists and overwrite declined."
                )
        except KeyboardInterrupt as e:
            raise FfmpegProcessInterruptedError(
                "[KeyboardInterrupt] FFmpeg process cancelled during overwrite prompt."
            ) from e
        except EOFError as e:
            raise FfmpegProcessInterruptedError(
                "Input error (EOF) during overwrite prompt. FFmpeg process cancelled."
            ) from e

    def __init__(
        self,
        command: List[str],
        ffmpeg_log_level: Optional[Union[FfmpegLogLevel, str]] = None,
        ffmpeg_log_file: Optional[Union[str, os.PathLike]] = None,
        print_detected_duration: bool = False,
        duration_override: Optional[float] = None,
        overwrite: Optional[bool] = None,
    ):
        """
        Create an FFmpeg process with progress reporting.

        Args:
            command:
                FFmpeg command as a list of arguments.
            ffmpeg_log_level:
                FFmpeg log level enum or case-insensitive string.
            ffmpeg_log_file:
                File path or file-like object used for FFmpeg stderr.
            print_detected_duration:
                Print the duration used for progress calculation.
            duration_override:
                Specify input file duration in seconds to use for progress calculation, instead of trying to detect this automatically with FFprobe. This is useful for partial, damaged, streamed, or
                synthetic inputs whose duration cannot be detected correctly.
            overwrite:
                What to do if the output file already exists. True overwrites it, False raises
                FfmpegCommandError, and None (the default) asks the user. Ignored if the command
                contains -y or -n.
        """
        validate_ffmpeg_command(command)

        ffmpeg_log_level_val: str

        if ffmpeg_log_level is None:
            ffmpeg_log_level_val = FfmpegLogLevel.VERBOSE.value
        elif isinstance(ffmpeg_log_level, FfmpegLogLevel):
            ffmpeg_log_level_val = ffmpeg_log_level.value
        elif isinstance(ffmpeg_log_level, str):
            try:
                ffmpeg_log_level_val = FfmpegLogLevel(ffmpeg_log_level.lower()).value
            except ValueError:
                valid_levels = [e.value for e in FfmpegLogLevel]
                raise FfmpegCommandError(
                    f"Invalid ffmpeg_log_level string: "
                    f"'{ffmpeg_log_level}'. Must be one of "
                    f"{valid_levels} (case-insensitive)."
                )
        else:
            raise TypeError(
                "ffmpeg_log_level must be an FfmpegLogLevel enum instance, "
                f"a string, or None, not "
                f"{type(ffmpeg_log_level).__name__}"
            )

        self._ffmpeg_log_level_val = ffmpeg_log_level_val

        input_file_index = command.index("-i")
        input_file_path_str = command[input_file_index + 1]
        self._input_filepath = Path(input_file_path_str)

        # Assumes last argument is output.
        self._output_filepath = Path(command[-1])

        if ffmpeg_log_file is None:
            if is_lavfi_input(command, input_file_index):
                # A filtergraph such as "testsrc2=size=1920x1080" can contain characters that
                # are not valid in filenames (e.g. ":" on Windows), so name the log after the
                # source instead.
                source_name = _safe_filename(input_file_path_str.split("=", 1)[0])
                self._ffmpeg_log_file = Path(f"lavfi_{source_name}_ffmpeg_log.txt")
            elif input_file_path_str == "-":
                self._ffmpeg_log_file = Path("stdin_ffmpeg_log.txt")
            elif is_local_file_input(command, input_file_index):
                self._ffmpeg_log_file = Path(f"{self._input_filepath.name}_ffmpeg_log.txt")
            else:
                # URLs and other protocols (e.g. "pipe:0") can contain characters that are not
                # valid in filenames, such as ":" or "?".
                name = self._input_filepath.name or input_file_path_str
                self._ffmpeg_log_file = Path(f"{_safe_filename(name)}_ffmpeg_log.txt")
        elif isinstance(ffmpeg_log_file, (str, os.PathLike)):
            self._ffmpeg_log_file = Path(ffmpeg_log_file)
        else:
            self._ffmpeg_log_file = ffmpeg_log_file

        self._print_detected_duration = print_detected_duration

        if duration_override is not None:
            if isinstance(duration_override, bool):
                raise TypeError("duration_override must be a number of seconds, not bool")

            try:
                duration_value = float(duration_override)
            except (TypeError, ValueError) as e:
                raise TypeError("duration_override must be a number of seconds or None") from e

            if not math.isfinite(duration_value) or duration_value <= 0:
                raise ValueError("duration_override must be a finite number greater than 0")

            self._duration_secs = duration_value
        elif is_stdin_input(input_file_path_str):
            # Running FFprobe on standard input would consume data that is meant for FFmpeg.
            self._duration_secs = None
        else:
            self._duration_secs = get_media_duration(input_file_path_str)

        input_duration_secs = self._duration_secs

        # Account for trimming (-ss, -sseof, -t, -to) so the progress bar reflects the
        # duration of the output rather than the whole input.
        if self._duration_secs is not None:
            self._duration_secs = get_expected_output_duration(command, self._duration_secs)

        if duration_override is not None:
            print(f"Using duration override: {input_duration_secs:.2f} seconds")
        elif self._print_detected_duration:
            if self._duration_secs is None:
                print("Could not detect duration. Progress bar may not show time remaining.")
            else:
                print(f"Detected duration: {input_duration_secs:.2f} seconds")

        if (
            self._duration_secs is not None
            and self._duration_secs != input_duration_secs
            and (duration_override is not None or self._print_detected_duration)
        ):
            print(f"Expected output duration after trimming: {self._duration_secs:.2f} seconds")

        self._ffmpeg_command = [
            command[0],
            "-hide_banner",
            "-loglevel",
            self._ffmpeg_log_level_val,
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        self._ffmpeg_command.extend(command[1:])

        if overwrite is not None and not isinstance(overwrite, bool):
            raise TypeError("overwrite must be True, False or None")

        user_args = command[1:]
        if _FFMPEG_OVERWRITE_FLAG not in user_args and self._output_filepath.exists():
            if _FFMPEG_NO_OVERWRITE_FLAG in user_args or overwrite is False:
                raise FfmpegCommandError(
                    f"Output file {self._output_filepath} already exists and overwriting is "
                    "disabled."
                )
            elif overwrite:
                self._ffmpeg_command.insert(1, _FFMPEG_OVERWRITE_FLAG)
            elif is_stdin_input(input_file_path_str):
                # Prompting would read from standard input, which carries FFmpeg's input.
                raise FfmpegCommandError(
                    f"Output file {self._output_filepath} already exists. Pass overwrite=True "
                    "or add -y to the command to overwrite it."
                )
            else:
                self._handle_overwrite_prompt()

        self._process: Optional[subprocess.Popen] = None
        self.use_tqdm: bool = False

    def run(
        self,
        print_command: bool = False,
    ) -> None:
        if print_command:
            print(f"Executing: {shlex.join(self._ffmpeg_command)}")

        # Run FFmpeg in its own process group, so that terminating the group on
        # KeyboardInterrupt does not also terminate this Python process.
        popen_kwargs = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            if isinstance(self._ffmpeg_log_file, Path):
                with open(
                    self._ffmpeg_log_file,
                    "w",
                    encoding="utf-8",
                ) as f:
                    self._process = subprocess.Popen(
                        self._ffmpeg_command,
                        stdout=subprocess.PIPE,
                        stderr=f,
                        **popen_kwargs,
                    )
            else:
                self._process = subprocess.Popen(
                    self._ffmpeg_command,
                    stdout=subprocess.PIPE,
                    stderr=self._ffmpeg_log_file,
                    **popen_kwargs,
                )
        except Exception as e:
            raise FfmpegProcessError(f"Error starting FFmpeg process: {e}") from e

        try:
            if self.use_tqdm:
                use_tqdm(self, self._process)
            else:
                use_rich(self, self._process)
        except KeyboardInterrupt as e:
            terminate_ffmpeg_process(self._process)
            raise FfmpegProcessInterruptedError(
                "[KeyboardInterrupt] FFmpeg process cancelled."
            ) from e
        finally:
            if self._process and self._process.stdout:
                self._process.stdout.close()
