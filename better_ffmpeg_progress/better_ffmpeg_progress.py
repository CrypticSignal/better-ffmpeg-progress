from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from typing import Callable, List, Optional, Union

from ffmpeg import probe
from tqdm import tqdm


@dataclass
class FfmpegProgress:
    """Data class to store FFmpeg progress information."""
    percentage: float = 0.0
    speed: float = 0.0
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

    def __init__(self, command: List[str], ffmpeg_loglevel: str = "verbose"):
        if "-i" not in command:
            raise ValueError("FFmpeg command must include '-i'")

        self._ffmpeg_args = command + ["-hide_banner", "-loglevel", ffmpeg_loglevel]
        self._output_filepath = Path(command[-1])
        self._progress = FfmpegProgress()
        self._duration_secs: Optional[float] = None
        self._current_size: int = 0
        self._previous_seconds_processed: float = 0
        self._progress_bar: Optional[tqdm] = None
        
        self._get_input_file_duration()

    def _get_input_file_duration(self) -> None:
        """Use ffprobe to get the duration of the input file"""
        index_of_filepath = self._ffmpeg_args.index("-i") + 1
        self._input_filepath = Path(self._ffmpeg_args[index_of_filepath])

        try:
            self._duration_secs = round(float(probe(self._input_filepath)["format"]["duration"]), 2)
            print(f"The duration of {self._input_filepath.name} has been detected as {self._duration_secs} seconds")
            # -progress pipe:1 sends progress metrics to stdout AND -stats_period sets the period at which encoding progress/statistics are updated
            # -nostats disables encoding progress/statistics in stderr
            self._ffmpeg_args.extend(["-progress", "pipe:1", "-stats_period", "0.1", "-nostats"])
        except Exception:
            print(f"Could not detect the duration of {self._input_filepath.name}. Percentage progress, ETA and estimated filesize will be unavailable.")
            self._duration_secs = None

    def _check_output_exists(self) -> bool:
        """Check if output file exists and handle overwrite prompt."""
        if self._output_filepath.exists() and "-y" not in self._ffmpeg_args:
            choice = input(f"{self._output_filepath} already exists. Overwrite? [Y/N]: ").lower()
            if choice != "y":
                print("FFmpeg process cancelled. Output file exists and overwrite declined.")
                return False
            self._ffmpeg_args.insert(1, "-y")
        return True

    def _update_progress(self, line: str, metric: str, value: str, 
                        progress_handler: Optional[Callable]) -> None:
        """Update progress information based on FFmpeg output."""
        if metric == "total_size":
            self._current_size = int(value)
        
        elif metric == "out_time_ms":
            seconds_processed = round((int(value) / 1_000_000), 2)
            
            if progress_handler is None and self._progress_bar:
                seconds_increase = seconds_processed - self._previous_seconds_processed
                self._progress_bar.update(seconds_increase)
                self._previous_seconds_processed = seconds_processed
                return

            if self._duration_secs:
                self._progress.percentage = (seconds_processed / self._duration_secs) * 100
                if self._current_size and self._progress.percentage > 0:
                    self._progress.estimated_size = int(self._current_size * (100 / self._progress.percentage))

        elif metric == "speed":
            speed_str = value.rstrip('x')
            if speed_str != "0":
                self._progress.speed = float(speed_str)
                if self._duration_secs:
                    seconds_remaining = self._duration_secs - (self._previous_seconds_processed or 0)
                    self._progress.eta = seconds_remaining / self._progress.speed

        if line == "progress=end":
            self._progress.percentage = 100
            self._progress.eta = 0

        if progress_handler:
            progress_handler(
                self._progress.percentage,
                self._progress.speed,
                self._progress.eta,
                self._progress.estimated_size
            )

    @staticmethod
    def _handle_pipe(pipe, queue: Queue) -> None:
        """Read from pipe and put lines into queue."""
        try:
            for line in pipe:
                queue.put(line.strip())
        finally:
            pipe.close()

    def _write_ffmpeg_output(self, stderr_output: str, output_file: Optional[Union[str, Path]]) -> None:
        """Write FFmpeg stderr to a txt file."""
        output_dir = Path("ffmpeg_output")
        output_dir.mkdir(exist_ok=True)
        
        log_file = output_file or output_dir / f"[{self._input_filepath.name}].txt"
        log_file = Path(log_file)
        
        log_file.write_text(stderr_output)
        print(f"Done! FFmpeg output logged to: {log_file}")

    def run(self, 
            output_file: Optional[Union[str, Path]] = None,
            progress_handler: Optional[Callable] = None,
            success_handler: Optional[Callable] = None,
            error_handler: Optional[Callable] = None) -> None:
        """
        Args:
            output_file: Optional filepath to write FFmpeg output to
            progress_handler: Optional function which receives progress metrics
            success_handler: Optional function to handle successful completion of the FFmpeg process
            error_handler: Optional function for FFmpeg process error handling
        """
        if not self._check_output_exists():
            return

        print(f"Executing: {' '.join(self._ffmpeg_args)}")

        if self._duration_secs and not progress_handler:
            self._progress_bar = tqdm(
                total=self._duration_secs,
                unit="s",
                dynamic_ncols=True,
                leave=False
            )

        process = subprocess.Popen(
            self._ffmpeg_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout_queue, stderr_queue = Queue(), Queue()
        # These threads put FFmpeg stdout and stderr into the queues
        Thread(target=self._handle_pipe, args=(process.stdout, stdout_queue), daemon=True).start()
        Thread(target=self._handle_pipe, args=(process.stderr, stderr_queue), daemon=True).start()

        stderr_output = []

        try:
            while process.poll() is None:
                # Handle stdout (progress metrics are sent here due as we are passing the -progress pipe:1 options to FFmpeg)
                try:
                    stdout = stdout_queue.get_nowait()
                    if stdout:
                        try:
                            metric, value = stdout.split("=")
                            if metric in self.WANTED_METRICS and value and "N/A" not in value:
                                self._update_progress(stdout, metric, value, progress_handler)
                        except ValueError:
                            continue
                except Empty:
                    pass
                # Handle stderr (regular FFmpeg output)
                try:
                    stderr = stderr_queue.get_nowait()
                    if "No such file" in stderr:
                        raise FileNotFoundError(f"Input file not found: {self._input_filepath}")
                    stderr_output.append(stderr)
                except Empty:
                    pass

            if process.returncode != 0:
                if error_handler:
                    error_handler()
                else:
                    sys.exit("\nFFmpeg process failed")

            if success_handler:
                success_handler()

        finally:
            if self._progress_bar:
                self._progress_bar.close()
            
            self._write_ffmpeg_output("\n".join(stderr_output), output_file)