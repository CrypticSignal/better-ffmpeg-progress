# better-ffmpeg-progress
Runs an FFmpeg command and shows the following in the terminal:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`

**Installation:**

`pip3 install better-ffmpeg-progress`

**Usage:**

Simply import the `run_ffmpeg_show_progress` function and supply a list of arguments like you would to `subprocess.run()`
```py
from better_ffmpeg_progress import run_ffmpeg_show_progress
run_ffmpeg_show_progress(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])
```
An optional `ffmpeg_loglevel` argument can be supplied, to set the value of FFmpeg's `-loglevel` option. Here's an example:

```
run_ffmpeg_show_progress(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"], ffmpeg_loglevel="warning")
```
