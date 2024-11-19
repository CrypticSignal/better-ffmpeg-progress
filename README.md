<div align="center">

[![PyPI downloads](https://img.shields.io/pypi/dm/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/better-ffmpeg-progress)
[![PyPI downloads](https://img.shields.io/pypi/dd/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/better-ffmpeg-progress)
![PyPI - Version](https://img.shields.io/pypi/v/better-ffmpeg-progress)
[![GitHub](https://img.shields.io/github/license/crypticsignal/better-ffmpeg-progress?label=License&color=blue)](LICENSE.txt)

# Better FFmpeg Progress
Runs an FFmpeg command and shows a progress bar with percentage progress, time elapsed and ETA.
</div>

FFmpeg outputs something like:
```
frame=  692 fps= 58 q=28.0 size=    5376KiB time=00:00:28.77 bitrate=1530.3kbits/s speed=2.43x
```
Better FFmpeg Progress outputs something like:
```
⠏ Processing abc.webm ━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  23% 0:00:04 00:15
```
Where:
- `Processing abc.webm` is the description of the progresss bar.
- `23%` is the percentage progress.
- `0:00:04` is the time (H:MM:SS) elapsed.
- `00:15` is the estimated time until the FFmpeg process completes.

As you can see, the output of Better FFmpeg Progress is much more useful.

## Installation
```
pip install better-ffmpeg-progress --upgrade
```

## Usage
Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would to `subprocess.run()`.

Simple Example:
```py
from better_ffmpeg_progress import FfmpegProcess
# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])
# Use the run method to run the FFmpeg command.
process.run()
```

Advanced Example:
```py
from better_ffmpeg_progress import FfmpegProcess

def handle_progress_info(percentage, speed, eta, estimated_filesize):
    print(f"Estimated Output Filesize: {estimated_filesize / 1_000_000} MB")

def handle_success():
  # Code to run if the FFmpeg process completes successfully.
  pass

def handle_error():
  # Code to run if the FFmpeg process encounters an error.
  pass

# Pass a list of FFmpeg arguments, like you would if using subprocess.run() or subprocess.Popen()
process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])

# Use the run method to run the FFmpeg command.
process.run(
    progress_bar_description="Converting file...",
    progress_handler=handle_progress_info,
    log_file="ffmpeg_log.txt",
    success_handler=handle_success,
    error_handler=handle_error,
)
```

## Optional Arguments
An instance of the `FfmpegProcess` class takes the following **optional** arguments:

- `ffmpeg_loglevel`: Desired FFmpeg log level. Default: "verbose"
- `print_stderr_new_line`: If better progress information cannot be shown, print FFmpeg stderr in a new line instead of replacing the current line in the terminal. Default: False
- `print_detected_duration`: Print the detected duration of the input file. Default: True

The `run` method takes the following **optional** arguments:
- `progress_bar_description` - An optional string to set a custom description for the progress bar. The default description is `Processing <file>`. This can be an empty string if you don't want the progress bar to have a description.
- `progress_handler`
  - You can create a function if you would like to do something with the following values:
    - Percentage progress. [float]
    - Speed, e.g. `22.3x` which means that 22.3 seconds of the input are processed every second. [string]
    - ETA in seconds. [float]
    - Estimated output filesize in bytes. [float]
      - _Note: This is not accurate. Please take the value with a grain of salt._

    The values will be `None` if unknown. The function will receive the current values of these metrics as arguments, every 0.1s.

- `log_file` -  The filepath to save the FFmpeg log to.
- `success_handler` - A function to run if the FFmpeg process completes successfully.
- `error_handler` - A function to run if the FFmpeg process encounters an error.