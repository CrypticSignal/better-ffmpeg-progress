from dataclasses import dataclass
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from typing import Callable, List, Optional, Union

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
        ffmpeg_loglevel: Desired FFmpeg log level. Default is "verbose".

    Raises:
        FileNotFoundError: If FFmpeg cannot find the input filepath or filename.
        ValueError: If the list of arguments does not include "-i"
    """

    WANTED_METRICS = frozenset({"out_time_ms", "total_size", "speed"})

    def __init__(
        self,
        command: List[str],
        ffmpeg_loglevel: str = "verbose",
        print_detected_duration: bool = True,
    ):
        if "-i" not in command:
            raise ValueError("FFmpeg command must include '-i'")

        self._ffmpeg_args = command + ["-hide_banner", "-loglevel", ffmpeg_loglevel]
        self._ffmpeg_stderr: List[str] = []
        self._output_filepath = Path(command[-1])
        self._print_detected_duration = print_detected_duration
        self._metrics = Metrics()
        self._duration_secs: Optional[float] = None
        self._current_size: int = 0

        self._get_input_file_duration()

    def _get_input_file_duration(self) -> None:
        """Use ffprobe to get the duration of the input file"""
        index_of_filepath = self._ffmpeg_args.index("-i") + 1
        self._input_filepath = Path(self._ffmpeg_args[index_of_filepath])

        try:
            self._duration_secs = float(
                probe(self._input_filepath)["format"]["duration"]
            )

            if self._print_detected_duration:
                print(
                    f"The duration of {self._input_filepath.name} has been detected as {self._duration_secs} seconds"
                )

            # -progress pipe:1 sends progress metrics to stdout AND -stats_period sets the period at which encoding progress/statistics are updated
            self._ffmpeg_args.extend(["-progress", "pipe:1", "-stats_period", "0.1"])
        except Exception:
            print(
                f"Could not detect the duration of '{self._input_filepath.name}'. Percentage progress, ETA and estimated filesize will be unavailable.\n",
            )

    def _check_output_exists(self) -> bool:
        """Check if output file exists and handle overwrite prompt."""
        if self._output_filepath.exists() and "-y" not in self._ffmpeg_args:
            choice = input(
                f"{self._output_filepath} already exists. Overwrite? [Y/N]: "
            ).lower()
            if choice != "y":
                print(
                    "FFmpeg process cancelled. Output file exists and overwrite declined."
                )
                return False
            self._ffmpeg_args.insert(1, "-y")
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

    def _write_ffmpeg_output(
        self,
        stderr_output: str,
        log_file: Optional[Union[str, Path]],
        is_error: bool = False,
    ) -> None:
        """Write FFmpeg stderr to a txt file."""
        Path(log_file).write_text(stderr_output)

        if is_error:
            return

        print(
            f"{"\n\n" if self._duration_secs is None else ""}FFmpeg log filename: {log_file}"
        )

    def _start_process(
        self,
        progress_bar: Optional[Progress],
        task_id: Optional[int],
        progress_handler: Optional[Callable],
    ) -> None:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

        process = subprocess.Popen(
            self._ffmpeg_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            creationflags=creationflags,
        )

        stdout_queue, stderr_queue = Queue(), Queue()
        Thread(
            target=self._handle_pipe, args=(process.stdout, stdout_queue), daemon=True
        ).start()
        Thread(
            target=self._handle_pipe, args=(process.stderr, stderr_queue), daemon=True
        ).start()

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

                    if self._duration_secs is None:
                        print(stderr, end="\r")

                    self._ffmpeg_stderr.append(stderr)
                except Empty:
                    pass

        except KeyboardInterrupt:
            self._kill_process_and_children(process.pid)
            sys.exit("[KeyboardInterrupt] FFmpeg process(es) killed.")

        return process.returncode

    def run(
        self,
        log_file: Optional[Union[str, Path]] = None,
        progress_bar_description: str = None,
        progress_handler: Optional[Callable] = None,
        success_handler: Optional[Callable] = None,
        error_handler: Optional[Callable] = None,
    ) -> None:
        """
        Args:
            log_file: Optional filepath to write FFmpeg output to
            progress_bar_description: Optional string to set a custom description for the progress bar
            progress_handler: Optional function which receives progress metrics
            success_handler: Optional function to handle successful completion of the FFmpeg process
            error_handler: Optional function for FFmpeg process error handling
        """
        if not self._check_output_exists():
            return

        print(
            f"Executing: {' '.join(self._ffmpeg_args)}{"\n" if self._duration_secs is None else ""}"
        )

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
        else:
            return_code = self._start_process(
                None,
                None,
                progress_handler,
            )

        self._handle_process_ended(
            return_code, error_handler, success_handler, log_file
        )

    def _handle_process_ended(
        self, return_code, error_handler, success_handler, log_file
    ):
        if return_code != 0:
            if error_handler:
                error_handler()

            ffmpeg_log_file = "ffmpeg_log.txt"

            self._write_ffmpeg_output(
                "\n".join(self._ffmpeg_stderr), ffmpeg_log_file, is_error=True
            )

            sys.exit(f"FFmpeg process failed. Check out {ffmpeg_log_file} for details")

        if log_file:
            self._write_ffmpeg_output("\n".join(self._ffmpeg_stderr), log_file)

        if success_handler:
            success_handler()
        else:
            print(
                f"{"\n" if self._duration_secs is None else ""}FFmpeg process completed."
            )

    def _kill_process_and_children(self, proc_pid):
        try:
            process = psutil.Process(proc_pid)
            for child in process.children(recursive=True):
                child.terminate()
            # Terminate the main process
            process.terminate()
        except psutil.NoSuchProcess:
            pass
