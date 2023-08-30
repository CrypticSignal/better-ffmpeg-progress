from better_ffmpeg_progress import FfmpegProcess


def handle_progress_info(percentage, speed, eta, estimated_filesize):
    print(percentage, speed, eta, estimated_filesize)
    # if estimated_filesize is not None:
    #     print(f"Estimated Output Filesize: {estimated_filesize / 1_000_000} MB")


# Pass a list of FFmpeg arguments, like you would if using subprocess.run()
process = FfmpegProcess(["ffmpeg", "-i", "6372305.mp4", "-c:a", "libmp3lame", "output.mp3"])
# Use the run method to run the FFmpeg command.
process.run(progress_handler=handle_progress_info)
