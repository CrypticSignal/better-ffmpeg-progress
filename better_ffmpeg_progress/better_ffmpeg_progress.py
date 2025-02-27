from enum import Enum
import os
from pathlib import Path
import psutil
import shutil
import subprocess
from typing import List, Optional, Union

from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)
from tqdm import tqdm

OUT_TIME_PREFIX = b"out_time_"
# Convert microseconds to seconds
MULTIPLIER = 1e-6


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
    @staticmethod
    def _validate_command(command: List[str]) -> bool:
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

    def _should_overwrite(self):
        if self._output_filepath.exists() and "-y" not in self._ffmpeg_command:
            try:
                if (
                    input(
                        f"{self._output_filepath} already exists. Overwrite? [Y/N]: "
                    ).lower()
                    != "y"
                ):
                    print(
                        "FFmpeg process cancelled. Output file exists and overwrite declined."
                    )
                    return False
            except EOFError:
                print("Input error. FFmpeg process cancelled.")
                return False
            except KeyboardInterrupt:
                print("[KeyboardInterrupt] FFmpeg process cancelled.")
                return False

            self._ffmpeg_command.insert(1, "-y")
            return True

    @staticmethod
    def _get_duration(filepath: Path) -> Optional[float]:
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
                    str(filepath),
                ],
                text=True,
            )
            return float(output)
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            return None

    @staticmethod
    def _check_shell_needed(command):
        shell_operators = {"|", ">", "<", ">>", "&&", "||"}
        return any(op in item for item in command for op in shell_operators)

    def __init__(
        self,
        command: List[str],
        ffmpeg_log_level: Optional[Union[FfmpegLogLevel, str]] = None,
        ffmpeg_log_file: Optional[Union[str, Path]] = None,
        print_detected_duration: bool = False,
        print_stderr_new_line: bool = False,
    ):
        if not self._validate_command(command):
            self._return_code = 1
            return

        if ffmpeg_log_level and ffmpeg_log_level not in FfmpegLogLevel:
            print(
                f"ffmpeg_log_level must be a lowercase variant of: {list(FfmpegLogLevel.__members__)}"
            )
            self._return_code = 1
            return

        input_idx = command.index("-i") + 1
        self._input_filepath = Path(command[input_idx])
        self._output_filepath = Path(command[-1])
        self._ffmpeg_log_level = (
            ffmpeg_log_level if ffmpeg_log_level else FfmpegLogLevel.VERBOSE.value
        )
        self._ffmpeg_log_file = Path(
            ffmpeg_log_file or f"{self._input_filepath.name}_log.txt"
        )
        self._print_detected_duration = print_detected_duration
        self._print_stderr_new_line = print_stderr_new_line
        self._duration_secs = self._get_duration(self._input_filepath)

        if self._print_detected_duration and self._duration_secs is not None:
            print(f"Detected duration: {self._duration_secs} seconds")

        self._ffmpeg_command = [
            command[0],
            "-hide_banner",
            "-loglevel",
            self._ffmpeg_log_level,
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        self._ffmpeg_command.extend(command[1:])

        if not self._should_overwrite():
            self._return_code = 1
            return

    def _use_rich(self, process) -> int:
        task_id = None

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(compact=True),
            refresh_per_second=2,
        ) as progress_bar:
            if self._duration_secs:
                task_id = progress_bar.add_task(
                    f"Processing {self._input_filepath.name}",
                    total=self._duration_secs,
                )

                update_progress = progress_bar.update
                duration = self._duration_secs

                for line in process.stdout:
                    if line[:9] == OUT_TIME_PREFIX:
                        value = line[12:-1]
                        # Check if the first byte is a digit
                        try:
                            if 48 <= value[0] <= 57:
                                value_int = int(value) * MULTIPLIER
                                if value_int <= duration:
                                    update_progress(task_id, completed=value_int)
                        except (IndexError, ValueError):
                            pass

            process.wait()

            if process.returncode == 0 and task_id is not None:
                update_progress(task_id, completed=duration)
                progress_bar.columns = (
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                )
                update_progress(
                    task_id,
                    description=f"✓ Processed {self._input_filepath.name}",
                )

            if process.returncode != 0:
                if task_id is not None:
                    progress_bar.update(
                        task_id,
                        description=f"FFmpeg process failed. Check out {self._ffmpeg_log_file} for details.",
                    )
                return 1

            return 0

    def _use_tqdm(self, process) -> int:
        progress_bar = None

        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80

        if self._duration_secs:
            progress_bar = tqdm(
                mininterval=0.5,
                total=self._duration_secs,
                desc=f"Processing {self._input_filepath.name}",
                ncols=80,
                dynamic_ncols=True if width < 80 else False,
                bar_format="{desc} {bar} {percentage:.1f}% {elapsed} {remaining}",
            )

            duration = self._duration_secs

            for line in process.stdout:
                if line[:9] == OUT_TIME_PREFIX:
                    value = line[12:-1]
                    try:
                        # Check if the first byte is a digit
                        if 48 <= value[0] <= 57:
                            value_int = int(value) * MULTIPLIER
                            if value_int <= duration:
                                progress_bar.n = value_int
                                progress_bar.refresh()
                    except (IndexError, ValueError):
                        pass

        process.wait()

        if process.returncode == 0 and progress_bar is not None:
            progress_bar.n = duration
            progress_bar.set_description(f"✓ Processed {self._input_filepath.name}")
            progress_bar.close()

        if process.returncode != 0:
            print(
                f"FFmpeg process failed. Check out {self._ffmpeg_log_file} for details."
            )
            return 1

        return 0

    def run(
        self,
        print_command: bool = False,
        use_tqdm: bool = False,
    ) -> int:
        if hasattr(self, "_return_code") and self._return_code != 0:
            return 1

        if print_command:
            print(f"Executing: {' '.join(self._ffmpeg_command)}")

        self._shell_needed = self._check_shell_needed(self._ffmpeg_command)

        if self._shell_needed:
            self._ffmpeg_command = " ".join(self._ffmpeg_command)

        try:
            with open(self._ffmpeg_log_file, "w") as f:
                self._process = subprocess.Popen(
                    self._ffmpeg_command,
                    shell=self._shell_needed,
                    stdout=subprocess.PIPE,
                    stderr=f,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt"
                    else 0,
                )
        except Exception as e:
            print(f"Error starting FFmpeg process: {e}")
            return 1

        try:
            return (
                self._use_tqdm(self._process)
                if use_tqdm
                else self._use_rich(self._process)
            )
        except KeyboardInterrupt:
            print("\n[KeyboardInterrupt] Terminating FFmpeg process...")
            self._terminate()
            print("Done!")
            return 1
        finally:
            if self._process and self._process.poll() is None:
                self._terminate()

    def _terminate(self):
        if not self._process or self._process.poll() is not None:
            return

        try:
            proc = psutil.Process(self._process.pid)
            children = proc.children(recursive=True)

            # Windows. Use CTRL_BREAK_EVENT to terminate entire process group
            if os.name == "nt":
                if self._shell_needed:
                    # If running under a shell, terminate shell first
                    proc.terminate()
                else:
                    from signal import CTRL_BREAK_EVENT

                    # Send CTRL_BREAK_EVENT to entire process group
                    os.kill(self._process.pid, CTRL_BREAK_EVENT)
            # Unix
            else:
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                proc.terminate()

            # Wait up to 1 second for processes to exit gracefully
            gone, still_alive = psutil.wait_procs(children + [proc], timeout=1)

            # Force kill any remaining processes
            for p in still_alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

        except (psutil.NoSuchProcess, ProcessLookupError, KeyboardInterrupt):
            # As a last resort, force kill the main process
            self._process.kill()
