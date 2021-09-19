# better-ffmpeg-progress
A Python function that runs an FFmpeg command and shows the following in addition to the FFmpeg output:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`

# Usage
`run_ffmpeg_show_progress("ffmpeg -i input.mp4 -c:a libmp3lame output.mp3")`