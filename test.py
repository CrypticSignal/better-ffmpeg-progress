from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

command = [
    "ffmpeg",
    "-i",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-c:a",
    "copy",
    "-f",
    "null",
    "-",
]

try:
    process = FfmpegProcess(command)
    # Uncomment the line below if you want to use tqdm instead of rich for the progress bar
    # process.use_tqdm = True

    process.run()
    # The FFmpeg process failed
    if process.return_code != 0:
        pass
except FfmpegProcessError as e:
    print(f"An error occurred when running the better-ffmpeg-process package:\n{e}")
