import os
from pathlib import Path
import subprocess
import sys

from ffmpeg import probe
from tqdm import tqdm


class FfmpegProcess:
    def __init__(self, command, ffmpeg_loglevel="verbose"):
        """
        Creates the list of FFmpeg arguments.
        Accepts an optional ffmpeg_loglevel parameter to set the value of FFmpeg's -loglevel argument.
        """
        self._command = command
        index_of_filepath = self._command.index("-i") + 1
        self._filepath = self._command[index_of_filepath]

        self._can_get_duration = True

        try:
            self._duration_secs = float(probe(self._filepath)["format"]["duration"])
        except Exception:
            self._can_get_duration = False

        self._ffmpeg_args = self._command + ["-loglevel", ffmpeg_loglevel]

        if self._can_get_duration:
            # pipe:1 sends the progress to stdout. See https://stackoverflow.com/a/54386052/13231825
            self._ffmpeg_args += ["-progress", "pipe:1", "-nostats"]

    def run(self, progress_handler=None, ffmpeg_output_file=None):
        """
        Runs FFmpeg and prints the following:
            - Percentage Progress
            - Speed
            - ETA (minutes and seconds)
        Example:
        Progress: 25% | Speed: 22.3x | ETA: 1m 33s
        """

        if ffmpeg_output_file is None:
            os.makedirs("ffmpeg_output", exist_ok=True)
            ffmpeg_output_file = os.path.join("ffmpeg_output", f"[{Path(self._filepath).name}].txt")

        with open(ffmpeg_output_file, "w") as f:
            pass

        print(f"Running: {' '.join(self._ffmpeg_args)}")
        popen_args = [self._ffmpeg_args]

        if self._can_get_duration:

            with open(ffmpeg_output_file, "a") as f:
                self._process = subprocess.Popen(
                    self._ffmpeg_args, stdout=subprocess.PIPE, stderr=f
                )

            progress_bar = tqdm(total=self._duration_secs, unit="s", dynamic_ncols=True)
            progress_bar.clear()
            previous_seconds_processed = 0
        else:
            self._process = subprocess.Popen(self._ffmpeg_args)

        try:
            while self._process.poll() is None:
                if self._can_get_duration:
                    ffmpeg_output = self._process.stdout.readline().decode()
                    # A progress handler was not specified. Use tqdm to show a progress bar.
                    if progress_handler is None:
                        if "out_time_ms" in ffmpeg_output:
                            seconds_processed = int(ffmpeg_output.strip()[12:]) / 1_000_000
                            seconds_increase = seconds_processed - previous_seconds_processed
                            progress_bar.update(seconds_increase)
                            previous_seconds_processed = seconds_processed
                    # A progress handler was specified.
                    else:
                        if "out_time_ms" in ffmpeg_output:
                            seconds_processed = int(ffmpeg_output.strip()[12:]) / 1_000_000
                            percentage = round((seconds_processed / self._duration_secs) * 100, 1)

                        if "speed" in ffmpeg_output:
                            speed = ffmpeg_output.split("=")[1].strip()
                            if " " in speed or "N/A" in speed:
                                speed = None
                            else:
                                speed = float(speed[:-1])

                            if speed:
                                eta = (file_duration - secs) / speed
                                progress_handler(percentage, f"{speed}x", eta)

            progress_bar.close()
            print(f"Done! Check out /{ffmpeg_output_file} to see the FFmpeg output.")

        except KeyboardInterrupt:
            progress_bar.close()
            self._process.kill()
            print("[KeyboardInterrupt] FFmpeg process killed. Exiting Better FFmpeg Progress.")
            sys.exit(0)
