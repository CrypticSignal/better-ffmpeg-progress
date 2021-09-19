# better-ffmpeg-progress
A Python function that runs an FFmpeg command and shows the following in addition to the FFmpeg output:
- Percentage Progress
- Speed
- ETA (minutes and seconds)

Example: `Progress: 25% | Speed: 22.3x | ETA: 1m 33s`
    
The function takes the following arguments:
- The path of the file you wish to convert.
- The command you wish to run, e.g. `ffmpeg -i input.mp4 -c:a libmp3lame output.mp3`

# Usage
`run_ffmpeg_show_progress("input.mp4", "ffmpeg -i input.mp4 -c:a libmp3lame output.mp3")`
