import os
from pathlib import Path
import subprocess
import sys

from ffmpeg import probe
from tqdm import tqdm


class FfmpegProcess:
    """
    Args:
        command (list): A list of arguments to pass to FFmpeg.

        ffmpeg_loglevel (str, optional): Desired FFmpeg log level. Default is "verbose".

    Raises:
        ValueError: If the list of arguments does not include "-i".
    """

    def __init__(self, command, ffmpeg_loglevel="verbose"):
        if "-i" not in command:
            raise ValueError("FFmpeg command must include '-i'")

        self._ffmpeg_args = command + ["-hide_banner", "-loglevel", ffmpeg_loglevel]
        self._output_filepath = command[-1]

        self._set_file_info()

        self._estimated_size = None
        self._eta = None
        self._percentage_progress = 0
        self._previous_seconds_processed = 0
        self._progress_bar = None
        self._seconds_processed = 0
        self._speed = 0
        self._current_size = 0

    def _set_file_info(self):
        index_of_filepath = self._ffmpeg_args.index("-i") + 1
        self._filepath = self._ffmpeg_args[index_of_filepath]
        self._can_get_duration = True

        try:
            self._duration_secs = float(probe(self._filepath)["format"]["duration"])
            print(
                f"The duration of {self._filepath} has been detected as {self._duration_secs} seconds."
            )
        except Exception:
            self._can_get_duration = False

        if self._can_get_duration:
            self._ffmpeg_args += ["-progress", "pipe:1", "-nostats"]

    def _should_run_ffmpeg(self):
        dirname = os.path.dirname(self._output_filepath)
        self._dir_files = (
            [file for file in os.listdir(dirname)] if dirname else [file for file in os.listdir()]
        )

        if "-y" not in self._ffmpeg_args and self._output_filepath in self._dir_files:
            choice = input(f"{self._output_filepath} already exists. Overwrite? [Y/N]: ").lower()

            if choice != "y":
                print(
                    "FFmpeg will not run as the output filename already exists, and you do not want it to be overwritten."
                )
                return False

            self._ffmpeg_args.insert(1, "-y")
            return True

        return True

    def _update_progress(self, ffmpeg_output, progress_handler):
        if ffmpeg_output:
            value = ffmpeg_output.split("=")[1].strip()

            if progress_handler is None:
                if "out_time_ms" in ffmpeg_output:
                    seconds_processed = round(int(value) / 1_000_000, 1)
                    seconds_increase = seconds_processed - self._previous_seconds_processed
                    self._progress_bar.update(seconds_increase)
                    self._previous_seconds_processed = seconds_processed

            else:
                if "total_size" in ffmpeg_output and "N/A" not in value:
                    self._current_size = int(value)

                elif "out_time_ms" in ffmpeg_output:
                    self._seconds_processed = int(value) / 1_000_000

                    if self._can_get_duration:
                        self._percentage_progress = (
                            self._seconds_processed / self._duration_secs
                        ) * 100

                        if self._current_size is not None and self._percentage_progress != 0.0:
                            self._estimated_size = self._current_size * (
                                100 / self._percentage_progress
                            )

                elif "speed" in ffmpeg_output:
                    speed_str = value[:-1]

                    if speed_str != "0" and "N/A" not in value:
                        self._speed = float(speed_str)

                        if self._can_get_duration:
                            self._eta = (
                                self._duration_secs - self._seconds_processed
                            ) / self._speed

                if ffmpeg_output == "progress=end":
                    self._percentage_progress = 100
                    self._eta = 0

                progress_handler(
                    self._percentage_progress, self._speed, self._eta, self._estimated_size
                )

    def run(
        self,
        progress_handler=None,
        ffmpeg_output_file=None,
        success_handler=None,
        error_handler=None,
    ):
        if not self._should_run_ffmpeg():
            return

        if ffmpeg_output_file is None:
            os.makedirs("ffmpeg_output", exist_ok=True)
            ffmpeg_output_file = os.path.join("ffmpeg_output", f"[{Path(self._filepath).name}].txt")

        with open(ffmpeg_output_file, "a") as f:
            process = subprocess.Popen(self._ffmpeg_args, stdout=subprocess.PIPE, stderr=f)
            print(f"\nRunning: {' '.join(self._ffmpeg_args)}\n")

        if progress_handler is None and self._can_get_duration:
            self._progress_bar = tqdm(
                total=round(self._duration_secs, 1),
                unit="s",
                dynamic_ncols=True,
                leave=False,
            )

        try:
            while process.poll() is None:
                ffmpeg_output = process.stdout.readline().decode().strip()
                self._update_progress(ffmpeg_output, progress_handler)

            if process.returncode != 0:
                if error_handler:
                    error_handler()
                    return

                print(
                    f"The FFmpeg process encountered an error. The output of FFmpeg can be found in {ffmpeg_output_file}"
                )

            if success_handler:
                success_handler()

            print(f"\n\nDone! To see FFmpeg's output, check out {ffmpeg_output_file}")

        except KeyboardInterrupt:
            self._progress_bar.close()
            print("[KeyboardInterrupt] FFmpeg process killed.")
            sys.exit()

        except Exception as e:
            print(f"[Better FFmpeg Process] {e}")
