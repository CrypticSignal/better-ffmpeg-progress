from dataclasses import dataclass
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from typing import Callable, List, Optional, Union

from .utils import print_with_prefix

from ffmpeg import probe
import psutil
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    SpinnerColumn,
)


@dataclass
class Metrics:
    """Data class to store FFmpeg progress information."""

    percentage: float = 0.0
    seconds_processed: float = 0
    speed: float = None
    eta: Optional[float] = None
    estimated_size: Optional[int] = None


class FfmpegProcess:
    """
    Args:
        command: A list of arguments to pass to FFmpeg.
        ffmpeg_loglevel: Desired FFmpeg log level. Default: "verbose"
        print_stderr_new_line: If better progress information cannot be shown, print FFmpeg stderr in a new line instead of replacing the current line in the terminal. Default: False
        print_detected_duration: Print the detected duration of the input file. Default: True

    Raises:
        FileNotFoundError: If FFmpeg cannot find the input filepath or filename.
        ValueError: If the list of arguments does not include "-i"
    """

    WANTED_METRICS = frozenset({"out_time_ms", "total_size", "speed"})

    def __init__(
        self,
        command: List[str],
        ffmpeg_loglevel: str = "verbose",
        print_detected_duration: bool = False,
        print_stderr_new_line: bool = False,
    ):
        if "-i" not in command:
            raise ValueError("FFmpeg command must include '-i'")

        # -progress pipe:1 sends progress metrics to stdout
        # -stats_period sets the period at which encoding progress/statistics are updated
        extra_ffmpeg_options = [
            "-hide_banner",
            "-loglevel",
            ffmpeg_loglevel,
            "-progress",
            "pipe:1",
            "-stats_period",
            "0.1",
        ]

        command[1:1] = extra_ffmpeg_options

        self._ffmpeg_command = command
        self._output_filepath = Path(command[-1])
        self._print_detected_duration = print_detected_duration
        self._print_stderr_new_line = print_stderr_new_line
        self._metrics = Metrics()
        self._duration_secs: Optional[float]
        self._current_size: int = 0
        self._ffmpeg_log_file: Optional[Path] = None
        self._error_messages: list[str] = []
        self._get_input_file_duration()

    def _get_input_file_duration(self) -> None:
        """Use ffprobe to get the duration of the input file"""
        index_of_filepath = self._ffmpeg_command.index("-i") + 1
        self._input_filepath = Path(self._ffmpeg_command[index_of_filepath])

        try:
            self._duration_secs = float(
                probe(self._input_filepath)["format"]["duration"]
            )

            if self._print_detected_duration:
                print_with_prefix(
                    "[Better FFmpeg Progress] ",
                    f"The duration of {self._input_filepath.name} has been detected as {self._duration_secs} seconds",
                )

            # -nostats ensures that progress information is not sent to stderr as this info is not needed in the log file, e.g.
            # frame= 1381 fps=254 q=18.0 size=   46592KiB time=00:00:46.07 bitrate=8283.1kbits/s speed=8.47x
            self._ffmpeg_command.extend(["-nostats"])
        except Exception:
            print_with_prefix(
                "[Better FFmpeg Progress] ",
                f"Could not detect the duration of '{self._input_filepath.name}'. Percentage progress, ETA and estimated filesize will be unavailable.\n",
            )
            self._duration_secs = None

    def _should_overwrite(self) -> bool:
        if self._output_filepath.exists() and "-y" not in self._ffmpeg_command:
            choice = input(
                f"{self._output_filepath} already exists. Overwrite? [Y/N]: "
            ).lower()

            if choice != "y":
                print_with_prefix(
                    "[Better FFmpeg Progress] ",
                    "FFmpeg process cancelled. Output file exists and overwrite declined.",
                )
                return False

            self._ffmpeg_command.insert(1, "-y")

        return True

    def _update_metrics(
        self, line: str, metric: str, value: str, progress_handler: Optional[Callable]
    ) -> None:
        """Update progress information based on FFmpeg output."""
        if metric == "total_size":
            self._current_size = int(value)

        elif metric == "out_time_ms":
            self._metrics.seconds_processed = int(value) / 1_000_000

            if self._duration_secs:
                self._metrics.percentage = (
                    self._metrics.seconds_processed / self._duration_secs
                ) * 100
                if self._current_size and self._metrics.percentage > 0:
                    self._metrics.estimated_size = int(
                        self._current_size * (100 / self._metrics.percentage)
                    )

        elif metric == "speed":
            speed_float = float(value.rstrip("x"))
            if speed_float > 0:
                self._metrics.speed = float(speed_float)
                if self._duration_secs:
                    seconds_remaining = (
                        self._duration_secs - self._metrics.seconds_processed
                    )
                    self._metrics.eta = seconds_remaining / self._metrics.speed

        if line == "progress=end":
            self._metrics.percentage = 100
            self._metrics.eta = 0

        if progress_handler:
            progress_handler(
                self._metrics.percentage,
                self._metrics.speed,
                self._metrics.eta,
                self._metrics.estimated_size,
            )

    @staticmethod
    def _handle_pipe(pipe, queue: Queue) -> None:
        """Read from the pipe and put the lines into the queue."""
        try:
            for line in pipe:
                queue.put(line.strip())
        finally:
            pipe.close()

    def _contains_shell_operators(self, command: List[str]) -> bool:
        """Check if the command contains shell operators."""
        shell_operators = {"|", ">", "<", ">>", "&&", "||"}
        return any(op in command for op in shell_operators)

    def _start_process(
        self,
        progress_bar: Optional[Progress],
        task_id: Optional[int],
        progress_handler: Optional[Callable],
    ) -> int:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

        # If command contains shell operators, turn the list into a string.
        if self._contains_shell_operators(self._ffmpeg_command):
            final_command = " ".join(self._ffmpeg_command)
        else:
            final_command = self._ffmpeg_command

        self._write_to_log_file(
            f"This file contains the log for the following command:\n{final_command if isinstance(final_command, str) else ' '.join(final_command)}\n",
        )

        process = subprocess.Popen(
            final_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=isinstance(final_command, str),
            creationflags=creationflags,
        )

        stdout_queue, stderr_queue = Queue(), Queue()
        Thread(
            target=self._handle_pipe, args=(process.stdout, stdout_queue), daemon=True
        ).start()
        Thread(
            target=self._handle_pipe, args=(process.stderr, stderr_queue), daemon=True
        ).start()

        error_words = [
            "error",
            "failed",
            "invalid",
            "trailing",
            "unable",
            "unknown",
            "no such file",
            "permission denied",
            "not found",
            "unrecognized",
            "undefined",
            "unsupported",
            "does not exist",
            "missing",
            "not available",
            "cannot",
            "could not",
            "bad",
            "wrong",
            "forbidden",
        ]

        try:
            while process.poll() is None:
                if self._duration_secs is not None:
                    try:
                        stdout = stdout_queue.get_nowait()

                        if stdout:
                            metric, value = stdout.split("=")
                            if (
                                metric in self.WANTED_METRICS
                                and value
                                and "N/A" not in value
                            ):
                                self._update_metrics(
                                    stdout, metric, value, progress_handler
                                )
                                if (
                                    metric == "out_time_ms"
                                    and progress_bar
                                    and task_id is not None
                                ):
                                    progress_bar.update(
                                        task_id,
                                        completed=self._metrics.seconds_processed,
                                        speed=self._metrics.speed,
                                    )
                    except Empty:
                        pass

                try:
                    stderr = stderr_queue.get_nowait()

                    if stderr:
                        self._write_to_log_file(stderr)

                        if any(keyword in stderr.lower() for keyword in error_words):
                            self._error_messages.append(stderr)

                        if self._duration_secs is None:
                            print(
                                stderr,
                                end="\n" if self._print_stderr_new_line else "\r",
                                flush=True,
                            )
                except Empty:
                    pass

        except KeyboardInterrupt:
            self._kill_process_and_children(process.pid)
            self._write_to_log_file("\n[KeyboardInterrupt] FFmpeg process killed.")
            sys.exit("\n[KeyboardInterrupt] FFmpeg process killed.")

        # After the process ends, drain any remaining stderr
        while True:
            try:
                stderr = stderr_queue.get_nowait()
                if stderr:
                    self._write_to_log_file(stderr)

                    if any(keyword in stderr.lower() for keyword in error_words):
                        self._error_messages.append(stderr)

                    if self._duration_secs is None:
                        print(
                            stderr,
                            end="\n" if self._print_stderr_new_line else "\r",
                            flush=True,
                        )
            except Empty:
                break

        return process.returncode

    def run(
        self,
        log_file: Optional[Union[str, Path]] = "ffmpeg_log.txt",
        print_command=False,
        progress_bar_description: str = None,
        progress_handler: Optional[Callable] = None,
        success_handler: Optional[Callable] = None,
        error_handler: Optional[Callable] = None,
    ) -> None:
        """
        Args:
            log_file: Optional filepath to write FFmpeg output to
            print_command: Print the FFmpeg command being executed. Default: False
            progress_bar_description: Optional string to set a custom description for the progress bar
            progress_handler: Optional function which receives progress metrics
            success_handler: Optional function to handle successful completion of the FFmpeg process
            error_handler: Optional function for FFmpeg process error handling
        """
        if not self._should_overwrite():
            return

        self._ffmpeg_log_file = Path(log_file)

        with open(self._ffmpeg_log_file, "w"):
            pass

        if print_command:
            print(f"Executing: {' '.join(self._ffmpeg_command)}")

        if self._duration_secs and not progress_handler:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(compact=True),
                refresh_per_second=10,
            ) as progress_bar:
                task_id = progress_bar.add_task(
                    progress_bar_description
                    if progress_bar_description is not None
                    else f"Processing {self._input_filepath.name}",
                    total=self._duration_secs,
                )

                return_code = self._start_process(
                    progress_bar,
                    task_id,
                    None,
                )

                if return_code == 0:
                    progress_bar.columns = (
                        TextColumn("[progress.description]{task.description}"),
                    )
                    progress_bar.update(
                        task_id,
                        description=f"✓ Processed 100% of {self._input_filepath.name}",
                    )

        else:
            return_code = self._start_process(
                None,
                None,
                progress_handler,
            )

            if return_code == 0:
                print_with_prefix(
                    "\n" if self._duration_secs is None else "",
                    "FFmpeg process completed.",
                )

        self._handle_process_ended(return_code, error_handler, success_handler)

    def _handle_process_ended(
        self,
        return_code: int,
        error_handler: Optional[Callable],
        success_handler: Optional[Callable],
    ) -> None:
        """Handle the completion of the FFmpeg process."""
        if return_code != 0:
            if error_handler:
                error_handler()
                sys.exit(
                    "\nThe FFmpeg process encounted an error. Custom error handler executed."
                )

            print_with_prefix(
                "[Better FFmpeg Progress] ",
                f"FFmpeg process failed with return code {return_code}.\nError(s):",
            )
            print_with_prefix(
                "[Better FFmpeg Progress] ", "\n".join(self._error_messages)
            )
            print_with_prefix(
                "[Better FFmpeg Progress] ",
                f"Check out '{self._ffmpeg_log_file}' for more details.",
            )
            sys.exit(1)

        if success_handler:
            success_handler()

    def _kill_process_and_children(self, proc_pid: int) -> None:
        """Kill the FFmpeg process and its children."""
        try:
            process = psutil.Process(proc_pid)
            for child in process.children(recursive=True):
                child.terminate()
            # Terminate the main process
            process.terminate()
        except psutil.NoSuchProcess:
            pass

    def _write_to_log_file(self, message: str, mode: str = "a") -> None:
        if self._ffmpeg_log_file:
            with open(self._ffmpeg_log_file, mode) as f:
                f.write(f"{message}\n")
                f.flush()  # Ensure the message is written immediately
