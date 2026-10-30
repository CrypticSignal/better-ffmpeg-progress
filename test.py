import os

from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

DURATION_SECS = 30

command = [
    "ffmpeg",
    # Generate a 1080p test pattern with FFmpeg's built-in lavfi source, so no input file
    # is needed. To test a remote input instead, remove the next 4 arguments and use:
    # "-i", "https://media.xiph.org/video/derf/y4m/ducks_take_off_1080p50.y4m",
    "-f",
    "lavfi",
    "-i",
    f"testsrc2=duration={DURATION_SECS}:size=1920x1080:rate=30",
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    # Encode to a real format but discard the result by writing to the null device
    # (/dev/null, or NUL on Windows). Unlike "-f null", FFmpeg still reports the output size,
    # which is shown in the progress bar. -y skips the prompt to overwrite the null device.
    "-f",
    "matroska",
    "-y",
    os.devnull,
]

try:
    # FFprobe cannot detect the duration of a lavfi source, so it is provided manually.
    process = FfmpegProcess(command, duration_override=DURATION_SECS)
    # Uncomment the line below if you want to use tqdm instead of rich for the progress bar
    # process.use_tqdm = True

    process.run()
except FfmpegProcessError as e:
    print(f"An error occurred when running the better-ffmpeg-process package:\n{e}")
