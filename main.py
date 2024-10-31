from better_ffmpeg_progress import FfmpegProcess
from time import time

t1 = time()
# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(
    [
        "ffmpeg",
        "-i",
        # "abc.webm",
        "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
        "-c:v",
        "libx264",
        "-preset",
        "veryslow",
        "-y",
        "output.mp4",
    ],
    print_detected_duration=False,
    print_stderr_new_line=True,
)

# Use the run method to run the FFmpeg command.
process.run()
