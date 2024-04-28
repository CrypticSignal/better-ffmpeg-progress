<div align="center">

[![PyPI downloads](https://img.shields.io/pypi/dm/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/pypistats)
[![PyPI downloads](https://img.shields.io/pypi/dw/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/pypistats)
[![GitHub](https://img.shields.io/github/license/crypticsignal/better-ffmpeg-progress?label=License&color=blue)](LICENSE.txt)

# Better FFmpeg Progress

Runs an FFmpeg command and uses [tqdm](https://github.com/tqdm/tqdm) to show a progress bar.

</div>

## Example:

```
39%|███████████████████████████████████████████ | 23.6/60.2 [00:19<00:34, 1.07s/s]
```

Where:

- `39%` is the percentage progress.
- `23.6` seconds of the input file have been processed.
- `60.2` is the duration of the input file in seconds.
- `00:19` is the time elapsed since the FFmpeg process started.
- `00:34` is the estimated time required for the FFmpeg process to complete.
- `1.07` shows how many seconds of the input file are processed per second.

## Installation:

`pip3 install better-ffmpeg-progress --upgrade`

## Usage:

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

# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])

ffmpeg_output_path = 'ffmpeg_output.txt'

# Use the run method to run the FFmpeg command.
process.run(progress_handler=handle_progress_info, ffmpeg_output_file=ffmpeg_output_path, success_handler=handle_success, error_handler=handle_error)
```

The `run` method takes the following **optional** arguments:

- `progress_handler`

  - You can create a function if you would like to do something with the following values:

    - Percentage progress. [float]
    - Speed, e.g. `22.3x` which means that 22.3 seconds of the input are processed every second. [string]
    - ETA in seconds. [float]
    - Estimated output filesize in bytes. [float]
      - _Note: This is not accurate. Please take the value with a grain of salt._

    The values will be `None` if unknown. The function will receive the aforementioned metrics as arguments, about two times per second.

- `ffmpeg_output_file` - A string path to define where you want the output of FFmpeg to be saved. By default, this is saved in a folder named "ffmpeg_output", with the filename `[<input_filename>].txt`.

- `success_handler` - A function to run if the FFmpeg process completes successfully.

- `error_handler` - A function to run if the FFmpeg process encounters an error.

## Changelog:

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
