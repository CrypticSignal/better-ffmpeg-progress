from enum import Enum
import os
from pathlib import Path
import psutil
from queue import Queue
import shutil
import subprocess
from typing import List, Optional, Union

from ffmpeg import probe
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    SpinnerColumn,
)
from tqdm import tqdm


class FfmpegLogLevel(Enum):
    QUIET = "quiet"
    PANIC = "panic"
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    VERBOSE = "verbose"
    DEBUG = "debug"
    TRACE = "trace"


class FfmpegProcess:
    @classmethod
    def _validate_command(cls, command: List[str]) -> bool:
        if not shutil.which("ffmpeg"):
            print("Error: FFmpeg executable not found in PATH")
            return False

        if "-i" not in command:
            print("Error: FFmpeg command must include '-i'")
            return False

        input_idx = command.index("-i") + 1
        if input_idx >= len(command):
            print("Error: No input file specified after -i")
            return False

        input_file = Path(command[input_idx])
        if not input_file.exists():
            print(f"Error: Input file not found: {input_file}")
            return False

        if input_idx + 1 >= len(command):
            print("Error: No output file specified")
            return False

        return True

    def __init__(
        self,
        command: List[str],
        ffmpeg_log_level: Optional[FfmpegLogLevel] = None,
        ffmpeg_log_file: Optional[Union[str, Path]] = None,
        print_detected_duration: bool = False,
        print_stderr_new_line: bool = False,
    ):
        if not self._validate_command(command):
            self.return_code = 1
            return

        if ffmpeg_log_level and ffmpeg_log_level not in FfmpegLogLevel:
            print(
                f"ffmpeg_log_level must be a lowercase variant of: {list(FfmpegLogLevel.__members__)}"
            )
            self.return_code = 1
            return

        input_idx = command.index("-i") + 1
        self._input_filepath = Path(command[input_idx])
        self._output_filepath = Path(command[-1])
        self._ffmpeg_log_level = (
            ffmpeg_log_level if ffmpeg_log_level else FfmpegLogLevel.VERBOSE.value
        )
        self._ffmpeg_log_file = Path(
            ffmpeg_log_file
            if ffmpeg_log_file
            else f"{self._input_filepath.name}_log.txt"
        )
        self._print_detected_duration = print_detected_duration
        self._print_stderr_new_line = print_stderr_new_line

        try:
            probe_data = probe(self._input_filepath)
            self._duration_secs = float(probe_data["format"]["duration"])
            if self._print_detected_duration:
                print(f"Detected duration: {self._duration_secs} seconds")
        except Exception:
            self._duration_secs = None

        self._ffmpeg_command = [
            command[0],
            "-hide_banner",
            "-loglevel",
            self._ffmpeg_log_level,
            "-progress",
            "pipe:1",
            "-nostats",
            *command[1:],
        ]

        self.return_code = 0

    def _use_rich(self, process) -> int:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(compact=True),
            refresh_per_second=10,
        ) as progress_bar:
            task_id = None

            if self._duration_secs:
                task_id = progress_bar.add_task(
                    f"Processing {self._input_filepath.name}",
                    total=self._duration_secs,
                )

            if task_id is not None:
                while process.poll() is None:
                    stdout = process.stdout.readline()

                    if not stdout.startswith("out_time_ms"):
                        continue

                    try:
                        value = int(stdout.split("=")[1]) / 1_000_000
                    except ValueError:
                        continue
                    else:
                        if value <= self._duration_secs:
                            progress_bar.update(task_id, completed=value)

                if process.returncode == 0:
                    progress_bar.update(task_id, completed=self._duration_secs)
                    progress_bar.columns = (
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                    )
                    progress_bar.update(
                        task_id,
                        description=f"✓ Processed {self._input_filepath.name}",
                    )

            if process.returncode != 0:
                progress_bar.update(
                    task_id,
                    description=f"The FFmpeg process did not complete successfully. Check out {self._ffmpeg_log_file} for details.",
                )
                return 1

            return 0

    def _use_tqdm(self, process) -> int:
        progress_bar = None
        width, _ = os.get_terminal_size()

        if self._duration_secs:
            progress_bar = tqdm(
                total=self._duration_secs,
                desc=f"Processing {self._input_filepath.name}",
                ncols=80,
                dynamic_ncols=True if width < 80 else False,
                bar_format="{desc} {bar} {percentage:.1f}% {elapsed} {remaining}",
            )

        if progress_bar is not None:
            while process.poll() is None:
                stdout = process.stdout.readline()

                if not stdout.startswith("out_time_ms"):
                    continue

                try:
                    value = int(stdout.split("=")[1]) / 1_000_000
                except ValueError:
                    continue
                else:
                    if value <= self._duration_secs:
                        progress_bar.n = value
                        progress_bar.refresh()

            if process.returncode == 0:
                progress_bar.n = self._duration_secs
                progress_bar.set_description(f"✓ Processed {self._input_filepath.name}")

            progress_bar.close()

        if process.returncode != 0:
            print(
                f"The FFmpeg process did not complete successfully. Check out {self._ffmpeg_log_file} for details."
            )
            return 1

        return 0

    def run(
        self,
        print_command: bool = False,
        use_tqdm: bool = False,
    ) -> int:
        if hasattr(self, "return_code") and self.return_code != 0:
            return 1

        if self._output_filepath.exists() and "-y" not in self._ffmpeg_command:
            if (
                input(
                    f"{self._output_filepath} already exists. Overwrite? [Y/N]: "
                ).lower()
                != "y"
            ):
                print(
                    "FFmpeg process cancelled. Output file exists and overwrite declined."
                )
                return 1
            self._ffmpeg_command.insert(1, "-y")

        if print_command:
            print(f"Executing: {' '.join(self._ffmpeg_command)}")

        def _contains_shell_operators(command: List[str]) -> bool:
            shell_operators = {"|", ">", "<", ">>", "&&", "||"}
            return any(op in command for op in shell_operators)

        # If command contains shell operators, turn the list into a string.
        if _contains_shell_operators(self._ffmpeg_command):
            self._ffmpeg_command = " ".join(self._ffmpeg_command)

        try:
            with open(self._ffmpeg_log_file, "w") as f:
                process = subprocess.Popen(
                    self._ffmpeg_command,
                    shell=isinstance(self._ffmpeg_command, str),
                    stdout=subprocess.PIPE,
                    stderr=f,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt"
                    else 0,
                )
        except Exception as e:
            print(f"Error starting FFmpeg process: {e}")
            return 1

        try:
            if use_tqdm:
                return self._use_tqdm(process)
            else:
                return self._use_rich(process)
        except KeyboardInterrupt:
            try:
                psutil.Process(process.pid).terminate()
            except psutil.NoSuchProcess:
                pass
            return 1
