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

## Changelog
[19/09/2022]
- Add the ability to specify a `success_handler` argument, a function to run if the FFmpeg process completes successfully.
- Add 0.001 to tqdm's `total` parameter to prevent the chance of getting `TqdmWarning: clamping frac to range [0, 1]`

[21/12/2022]
- [v2.0.7] Fix `'estimated_size' referenced before assignment` error.
- [v2.0.7] The progress bar now uses 1 decimal place for seconds processed and total duration.

[22/12/2022]
- [v2.0.8] Add the ability to specify an `error_handler` argument, a function to run if the FFmpeg process encounters an error.
- [v2.0.9] Fix a typo (commit [da45a84](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/da45a8416856ab7d3c7b748db5703fa3dbc65f60))

[07/02/2022]
- [v2.1.0] [Update function name](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/572fe8a0d71957d00b833134a4d35170630203fa) to fix `'process_complete_handler' is not defined` error.

[05/11/2023]
- [v2.1.2] [Do not exit the Python interpreter after the FFmpeg process is complete](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/0a358810773835297faae688689c6e0d8a5859ae)

[22/04/2024]
- [v2.1.3] Fix issue [#20](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/20)

[28/04/2024]
- [v2.1.4] Fix issue [#21](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/21)

[02/05/2024]
- [v2.1.5] Fix issue [#23](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/23) and make an error message more specific. [Here](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/a6ef7f26d080b684144021301f3b2aa5e0834dae) is the relevant commit.

[18/10/2024]
- [v2.1.6] Notify the user if the input filepath or filename is incorrect.
- [v2.1.7] Refactor to use threads and queues.

[19/10/2024]
- [v2.1.8] Use [Rich](https://github.com/Textualize/rich) instead of [tqdm](https://github.com/tqdm/tqdm) and format code with [Ruff](https://github.com/astral-sh/ruff).

[20/10/2024]
- [v2.1.9] Do not clear the terminal before showing the progress bar.
- [v2.2.0] Add the ability to set a custom description for the progress bar.

[22/10/2024]
- [v2.2.1] Only create a log file if the `log_file` parameter is specified and always create a log file if the FFmpeg process fails.

[28/10/2024]
- [v2.2.2] Make printing the detected duration of the input file optional.

[29/10/2024]
- [v2.3.0] Set `shell=True` to support piping.
- [v2.3.1] Kill FFmpeg process(es) on KeyboardInterrupt

[31/10/2024]
- [v2.4.0] Print FFmpeg stderr if better progress information cannot be shown.
- [v2.4.0] Flush the stream when printing FFmpeg stderr to ensure that it is printed immediately.
- [v2.5.0] Add an option to print FFmpeg stderr on a new line if better progress information cannot be shown.

[11/11/2024]
- [v2.5.1] Print the correct log file.

[12/11/2024]
- [v2.5.2] Drain any remaining FFmpeg stderr after the process ends.
- [v2.5.3] Write FFmpeg stderr to the log file in real time.
- [v2.5.4] Include progress info in stderr if the duration of the input file cannot be detected.
- [v2.5.5] Print detected errors in the terminal and only set `shell=True` if shell operators are detected.

[13/11/2024]
- [v2.5.6] Detect a wider range of errors.

[18/11/2024]
- [v2.5.7] Fix syntax. Should fix issue #26