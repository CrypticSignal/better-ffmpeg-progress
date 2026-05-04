from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

command = [
    "ffmpeg",
    "-i",
    "https://media.xiph.org/video/derf/y4m/ducks_take_off_1080p50.y4m",
    "-map", 
    "0:V",
    "-c:V",
    "libx264",
    "-preset",
    "ultrafast",
    "-f",
    "null",
    "-",
]

try:
    process = FfmpegProcess(command)
    # Uncomment the line below if you want to use tqdm instead of rich for the progress bar
    # process.use_tqdm = True

    process.run()
except FfmpegProcessError as e:
    print(f"An error occurred when running the better-ffmpeg-process package:\n{e}")
