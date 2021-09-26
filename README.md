# better-ffmpeg-progress
A command line program that runs an FFmpeg command and shows the following in addition to the FFmpeg output:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`

# Usage
`python3 better_ffmpeg_progress.py -c "ffmpeg -i input.mp4 -c:a libmp3lame output.mp3"`

I have also included a function, which can be imported and used in your own Python program or script:

`run_ffmpeg_show_progress("ffmpeg -i input.mp4 -c:a libmp3lame output.mp3")`