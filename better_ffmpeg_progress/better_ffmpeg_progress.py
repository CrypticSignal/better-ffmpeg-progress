from argparse import ArgumentParser, RawTextHelpFormatter
import os
from pathlib import Path
import subprocess

from ffmpeg import probe


class FfmpegProcess:
    def __init__(self, command, ffmpeg_loglevel="verbose"):
        """
        Creates the list of FFmpeg arguments.
        Accepts an optional ffmpeg_loglevel parameter to set the value of FFmpeg's -loglevel argument.
        """
        self._command = command
        self._ffmpeg_args = command + ["-progress", "pipe:1", "-nostats", "-loglevel", ffmpeg_loglevel]

    def run(self, progress_handler=None, ffmpeg_output_file=None):
        """
        Runs FFmpeg and prints the following:
            - Percentage Progress
            - Speed
            - ETA (minutes and seconds)
        Example:
        Progress: 25% | Speed: 22.3x | ETA: 1m 33s
        """

        index_of_filepath = self._command.index("-i") + 1
        filepath = self._command[index_of_filepath]

        if ffmpeg_output_file is None:
            os.makedirs("ffmpeg_output", exist_ok=True)
            ffmpeg_output_file = os.path.join("ffmpeg_output", f"[{Path(filepath).name}].txt")

        with open(ffmpeg_output_file, "w") as f:
            pass

        try:
            file_duration = float(probe(filepath)["format"]["duration"])
        except Exception:
            can_get_duration = False
            print(f"\nUnable to get the duration of {filepath}:\nThe improved progress stats will not be shown.")
        else:
            can_get_duration = True

        percentage = "unknown"
        speed = "unknown"
        eta_string = "unknown"
        ffmpeg_stderr = ""

        print("Running FFmpeg...")

        with open(ffmpeg_output_file, "a") as f:
            self._process = subprocess.Popen(
                self._ffmpeg_args,
                stdout=subprocess.PIPE,
                stderr=f,
            )

        try:
            while self._process.poll() is None:           
                ffmpeg_output = self._process.stdout.readline().decode("utf-8").strip()

                if ffmpeg_output is not None:
                    if can_get_duration:
                        if "out_time_ms" in ffmpeg_output:
                            microseconds = int(ffmpeg_output[12:])
                            secs = microseconds / 1_000_000
                            if file_duration is not None:
                                percentage = round((secs / file_duration) * 100, 1)

                        elif "speed" in ffmpeg_output:
                            speed = ffmpeg_output.split("=")[1].strip()
                            speed = 0 if " " in speed or "N/A" in speed else float(speed[:-1])
                            if speed != 0:
                                eta = (file_duration - secs) / speed
                                minutes = int(eta / 60)
                                seconds = round(eta % 60)
                                eta_string = f"{minutes}m {seconds}s"

                            if progress_handler is None:
                                print(f"Progress: {percentage}% | Speed: {speed}x | ETA: {eta_string}", end="\r")
                            else:
                                progress_handler(percentage, f"{speed}x", eta)
                    # ffprobe was unable to get the duration of the input file.
                    else:
                        print(self._process.stderr.readline().decode().strip())

            width, height = os.get_terminal_size()
            print("\r" + " " * (width - 1) + "\r", end="")
            print("FFmpeg process complete.")

        except KeyboardInterrupt:
            self._process.kill()
            print("\nFFmpeg process killed.")
