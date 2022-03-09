<div align="center">

[![PyPI downloads](https://img.shields.io/pypi/dm/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/pypistats)
[![PyPI downloads](https://img.shields.io/pypi/dw/better-ffmpeg-progress?label=PyPI&color=blue)](https://pypistats.org/packages/pypistats)
[![GitHub](https://img.shields.io/github/license/crypticsignal/better-ffmpeg-progress?label=License&color=blue)](LICENSE.txt)

# Better FFmpeg Progress

Runs an FFmpeg command and uses [tqdm](https://github.com/tqdm/tqdm) to show a progress bar.

</div>

## Example

```
39%|███████████████████████████████████████████ | 23.581/60.226 [00:19<00:34, 1.07s/s]
```

Where:

- `39%` is the percentage progress.
- `23.581` seconds of the input file have been processed.
- `60.226` is the duration of the input file in seconds.
- `00:19` is the time elapsed since the FFmpeg process started.
- `00:34` is the estimated time required for the FFmpeg process to complete.
- `1.07` shows how many seconds of the input file are processed per second.

## Installation

`pip3 install better-ffmpeg-progress --upgrade`

## Usage

Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would to `subprocess.run()`:

```py
from better_ffmpeg_progress import FfmpegProcess
# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])
# Use the run method to run the FFmpeg command.
process.run()
```

The `run` method takes the following **optional** arguments:

- `progress_handler`

  - You can create a function if you would like to do something with the following values:

    - Percentage progress. [float]
    - Speed, e.g. `22.3x` which means that 22.3 seconds of the input are processed every second. [string]
    - ETA in seconds. [float]
    - Estimated output filesize in bytes. [float]
      - _Note: This is not accurate. Please take the value with a grain of salt._

    The function will receive the aforementioned metrics as arguments, about two times per second.

    Here's an example of a progress handler that you can create:

    ```py
    def handle_progress_info(percentage, speed, eta, estimated_filesize):
        print(f"The FFmpeg process is {percentage}% complete. ETA is {eta} seconds.")
        print(f"Estimated Output Filesize: {estimated_filesize / 1_000_000} MB")
    ```

    Then you simply set the value of the `progress_handler` argument to the name of your function, like so:

    ```py
    process.run(progress_handler=handle_progress_info)
    ```

- `ffmpeg_output_file`

  - The `ffmpeg_output_file` argument allows you define where you want the output of FFmpeg to be saved. By default, this is saved in a folder named "ffmpeg_output", with the filename `[<input_filename>].txt`, but you can change this using the `ffmpeg_output_file` argument.

Here's an example where both the `progress_handler` and `ffmpeg_output_file` parameters are used:

```py
process.run(progress_handler=handle_progress_info, ffmpeg_output_file="ffmpeg_log.txt")
```
