<div align="center">

# Better FFmpeg Progress
Runs an FFmpeg command and shows a progress bar with percentage progress, elapsed time and ETA.
</div>

FFmpeg outputs something like:
```
frame=  692 fps= 58 q=28.0 size=    5376KiB time=00:00:28.77 bitrate=1530.3kbits/s speed=2.43x
```
Better FFmpeg Progress outputs something like:
```
Processing abc.webm
(5.50 MB / ~451.67 MB) ━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3% 0:00:11 04:15
```
Where:
- `Processing abc.webm` is the description of the progresss bar.
- `(5.50 MB / ~451.67 MB)` is the current output size / estimated final output size.
- `3%` is the percentage progress.
- `0:00:11` is the time elapsed.
- `04:15` is the estimated time until the FFmpeg process completes.

## Usage
Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would when using `subprocess.run()` or `subprocess.Popen()`. Example:

```python
from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

command = [
    "ffmpeg",
    "-i",
    "https://media.xiph.org/video/derf/y4m/ducks_take_off_1080p50.y4m",
    "-map",
    "0:V",
    "-c:V",
    "libx264",
    "-preset",
    "ultrafast",
    "-f",
    "null",
    "-",
]

try:
    process = FfmpegProcess(command)
    # Uncomment this line to use tqdm instead of Rich.
    # process.use_tqdm = True

    process.run()
except FfmpegProcessError as e:
    print(
        "An error occurred when running Better FFmpeg Progress:\n"
        f"{e}"
    )
```

## Duration Override
By default, Better FFmpeg Progress detects the duration of the input file and uses it to calculate percentage progress and ETA.

For partial, damaged, streamed or synthetic inputs, FFmpeg may be unable to detect the duration correctly. In these cases, you can provide the duration manually using `duration_override`.

The value should be the duration of the input file, in seconds:

```python
from better_ffmpeg_progress import FfmpegProcess

command = [
    "ffmpeg",
    "-i",
    "partial-input.flv",
    "-c",
    "copy",
    "recovered-output.mkv",
]

process = FfmpegProcess(
    command,
    duration_override=1222.64,
    print_detected_duration=True,
)

process.run()
```

## Optional Arguments
An instance of `FfmpegProcess` accepts the following optional arguments:
* `ffmpeg_log_level` — Set a value for FFmpeg's `-loglevel` option. Default: `"verbose"`.
* `ffmpeg_log_file` — Filepath or file-like object to which FFmpeg stderr will be written. Default: `<input filename>_ffmpeg_log.txt`.
* `print_detected_duration` — Print the detected duration. Default: `False`.
* `duration_override` — Specify input file duration in seconds to use for progress calculation, instead of trying to detect this automatically with FFprobe. Default: `None`.

The `run` method accepts the following optional argument:
* `print_command` — Print the FFmpeg command being executed. Default: `False`.

## Using tqdm
By default, the [Rich](https://github.com/Textualize/rich) library is used to display a progress bar. [tqdm](https://github.com/tqdm/tqdm) can be used instead by setting `process.use_tqdm = True`:
```python
process = FfmpegProcess(command)
process.use_tqdm = True
process.run()
```
