from better_ffmpeg_progress import FfmpegProcess

# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(
    [
        "ffmpeg",
        "-i",
        "abc.webm",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "output.mp4",
    ]
)


def hello():
    print("yoyo")


# Use the run method to run the FFmpeg command.
process.run(success_handler=hello)
