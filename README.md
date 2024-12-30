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
Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would to `subprocess.run()` or `subprocess.Popen()`.

Here's a simple example:
```py
from better_ffmpeg_progress import FfmpegProcess

process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:v", "libx265", "output.mp4"])
# return_code will be 0 if the process completed successfully, otherwise it will be 1
return_code = process.run()
```
## Optional Arguments
An instance of the `FfmpegProcess` class takes the following **optional** arguments:

- `ffmpeg_log_level` - Desired FFmpeg log level. Default: `"verbose"`
- `ffmpeg_log_file` - The filepath to save the FFmpeg log to. Default: `<input filename>_log.txt`
- `print_detected_duration` - Print the detected duration of the input file. Default: `False`
- `print_stderr_new_line` - If better progress information cannot be shown, print FFmpeg stderr in a new line instead of replacing the current line in the terminal. Default: `False`

The `run` method takes the following **optional** argument:
- `print_command` - Print the FFmpeg command being executed. Default: `False`