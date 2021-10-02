# better-ffmpeg-progress
Runs an FFmpeg command and shows the following in the terminal:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`

**Installation:**

`pip3 install better-ffmpeg-progress`

**Usage:**

Simply import the `run_ffmpeg_show_progress` function and supply an FFmpeg command as an argument.
```py
from better_ffmpeg_progress import run_ffmpeg_show_progress
run_ffmpeg_show_progress("ffmpeg -i input.mkv -c:v libx264 -c:a copy output.mp4")
```