# better-ffmpeg-progress
Runs an FFmpeg command and shows the following in the terminal:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`

**Installation:**

`pip3 install better-ffmpeg-progress`

**Usage:**

Create an instance of the `FfmpegProcess` class and supply a list of arguments like you would to `subprocess.run()`
```py
from better_ffmpeg_progress import FfmpegProcess
# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])
# Use the run method to run the FFmpeg command. The progress information will be printed in the terminal.
process.run()
```

The `run` method takes the following optional arguments:

- `progress_handler`

    - You can create a function if you wish to do something specific with the percentage progress, speed and ETA rather than it being printed in the format `Progress: 25.6% | Speed: 22.3x | ETA: 1m 33s`.
    The function will receive:
        - percentage progress (float, 1 decimal place), e.g. `25.6`.
        - Speed (string), e.g. `22.3x`.
        - ETA in seconds (float), e.g. `4.68984375`.

    Here's an example:
    ```py
    def handle_progress_info(percentage, speed, eta):
        print(f"The FFmpeg process is {percentage}% complete. ETA is {eta} seconds based on the current speed ({speed}).)
    ```
    Then you simple set the value of the `progress_handler` argument to the name of your function, like so:
    ```py
    process.run(progress_handler=handle_progress_info)
    ```

- `ffmpeg_output_file`

    - The `ffmpeg_output_file` argument allows you define where you want the output of FFmpeg to be saved. By default, this is saved in a folder named "ffmpeg_output", with the filename `[<input_filename>].txt`, but you can change this using the `ffmpeg_output_file` argument.

Here's an example where both the `progress_handler` and `ffmpeg_output_file` parameters are used:
```py
process.run(progress_handler=handle_progress_info, ffmpeg_output_file="ffmpeg_log.txt")
```

