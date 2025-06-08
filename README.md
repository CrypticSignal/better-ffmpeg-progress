<div align="center">

[![PyPI downloads](https://img.shields.io/pypi/dm/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/better-ffmpeg-progress)
[![PyPI downloads](https://img.shields.io/pypi/dd/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/better-ffmpeg-progress)
![PyPI - Version](https://img.shields.io/pypi/v/better-ffmpeg-progress)
[![GitHub](https://img.shields.io/github/license/crypticsignal/better-ffmpeg-progress?label=License&color=blue)](LICENSE.txt)

# Better FFmpeg Progress
Runs an FFmpeg command and shows a progress bar with percentage progress, time elapsed and ETA.

The [Rich](https://github.com/Textualize/rich) library is used for the progress bar by default, [tqdm](https://github.com/tqdm/tqdm) will be used if you pass `use_tqdm=True` to the `run` method.
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
- `0:00:04` is the time elapsed.
- `00:15` is the estimated time until the FFmpeg process completes.

As you can see, the output of Better FFmpeg Progress is much more useful.

## Installation
```
pip install better-ffmpeg-progress --upgrade
```

## Usage
Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would to `subprocess.run()` or `subprocess.Popen()`.

Example:
```py
from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

command = [
    "ffmpeg",
    "-i",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-c:a",
    "copy",
    "-f",
    "null",
    "-",
]

try:
    process = FfmpegProcess(command)
    # Uncomment the line below if you want to use tqdm instead of rich for the progress bar
    # process.use_tqdm = True

    # Run the FFmpeg command and show a progress bar
    process.run()
    # The FFmpeg process failed if the return code is not 0
    if process.return_code != 0:
        pass
except FfmpegProcessError as e:
    print(f"An error occurred when running the better-ffmpeg-process package:\n{e}")
```
## Optional Arguments
An instance of the `FfmpegProcess` class takes the following **optional** arguments:

- `ffmpeg_log_level` - Desired FFmpeg log level. Default: `"verbose"`
- `ffmpeg_log_file` - The filepath to save the FFmpeg log to. Default: `<input filename>_log.txt`
- `print_detected_duration` - Print the detected duration of the input file. Default: `False`
- `print_stderr_new_line` - If better progress information cannot be shown, print FFmpeg stderr in a new line instead of replacing the current line in the terminal. Default: `False`

The `run` method takes the following **optional** arguments:
- `print_command` - Print the FFmpeg command being executed. Default: `False`