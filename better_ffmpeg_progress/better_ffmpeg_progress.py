import os
from pathlib import Path
import subprocess
from sys import exit
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
    check_shell_needed_for_command,
)
from .terminate_process import terminate_ffmpeg_process
from .progress_bars import use_rich, use_tqdm

_FFMPEG_OVERWRITE_FLAG = "-y"


class FfmpegProcess:
    def _handle_overwrite_prompt(self) -> None:
        """
        Handles the logic for overwriting an existing output file.
        Modifies self._ffmpeg_command to include -y if overwrite is confirmed.
        Raises FfmpegProcessUserCancelledError or FfmpegProcessInterruptedError if not proceeding.
        """
        try:
            answer = (
                input(
                    f"Output file {self._output_filepath} already exists. Overwrite? [y/N]: "
                )
                .strip()
                .lower()
            )
            if answer == "y":
                # Insert -y
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
        ffmpeg_log_file: Optional[Union[str, Path]] = None,
        print_detected_duration: bool = False,
    ):
        # Raises FfmpegCommandError if the command is invalid
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
                    f"Invalid ffmpeg_log_level string: '{ffmpeg_log_level}'. "
                    f"Must be one of {valid_levels} (case-insensitive)."
                )
        else:
            raise TypeError(
                f"ffmpeg_log_level must be an FfmpegLogLevel enum instance, a string, or None, "
                f"not {type(ffmpeg_log_level).__name__}"
            )
        self._ffmpeg_log_level_val = ffmpeg_log_level_val

        input_file_index = command.index("-i")
        input_file_path_str = command[input_file_index + 1]
        self._input_filepath = Path(input_file_path_str)
        # Assumes last argument is output
        self._output_filepath = Path(command[-1])

        self._ffmpeg_log_file = Path(
            ffmpeg_log_file or f"{self._input_filepath.name}_ffmpeg_log.txt"
        )
        self._print_detected_duration = print_detected_duration
        self._duration_secs = get_media_duration(input_file_path_str)

        if self._print_detected_duration and self._duration_secs is not None:
            print(f"Detected duration: {self._duration_secs:.2f} seconds")
        elif self._print_detected_duration and self._duration_secs is None:
            print(
                "Could not detect duration. Progress bar may not show time remaining."
            )

        self._ffmpeg_command = [
            command[0],
            "-hide_banner",
            "-loglevel",
            self._ffmpeg_log_level_val,
            "-progress",
            "pipe:1",  # stdout
            "-nostats",
        ]
        self._ffmpeg_command.extend(command[1:])

        is_overwrite_in_user_command = any(
            arg == _FFMPEG_OVERWRITE_FLAG for arg in command[1:]
        )

        if self._output_filepath.exists() and not is_overwrite_in_user_command:
            self._handle_overwrite_prompt()

        self._process: Optional[subprocess.Popen] = None
        self._return_code: Optional[int] = None
        self.use_tqdm: bool = False

    def run(
        self,
        print_command: bool = False,
    ) -> int:
        if print_command:
            cmd_str = (
                " ".join(self._ffmpeg_command)
                if isinstance(self._ffmpeg_command, list)
                else self._ffmpeg_command
            )
            print(f"Executing: {cmd_str}")

        self._shell_needed = check_shell_needed_for_command(
            self._ffmpeg_command
            if isinstance(self._ffmpeg_command, list)
            else [self._ffmpeg_command]
        )

        current_ffmpeg_command = self._ffmpeg_command
        if self._shell_needed and isinstance(current_ffmpeg_command, list):
            current_ffmpeg_command = " ".join(current_ffmpeg_command)

        self._return_code = 1

        try:
            with open(self._ffmpeg_log_file, "w", encoding="utf-8") as f:
                creationflags = 0

                if os.name == "nt":
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

                self._process = subprocess.Popen(
                    current_ffmpeg_command,
                    shell=self._shell_needed,
                    stdout=subprocess.PIPE,
                    stderr=f,
                    creationflags=creationflags,
                )
        except Exception as e:
            # self._return_code remains None as the process didn't start
            raise FfmpegProcessError(f"Error starting FFmpeg process: {e}") from e

        try:
            if self.use_tqdm:
                self._return_code = use_tqdm(self, self._process)
            else:
                self._return_code = use_rich(self, self._process)
        except KeyboardInterrupt:
            self._terminate()
            self._return_code = 1
        finally:
            if self._process:
                self._return_code = self._process.returncode

                if self._process.stdout:
                    self._process.stdout.close()

        return self._return_code

    def _terminate(self):
        if self._process:
            terminate_ffmpeg_process(self._process)
        else:
            exit()

    @property
    def return_code(self) -> Optional[int]:
        """
        The return code of the FFmpeg process.
        None if the process has not started or failed to start.
        """
        return self._return_code
