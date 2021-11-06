from argparse import ArgumentParser, RawTextHelpFormatter
import subprocess

from ffmpeg import probe


def run_ffmpeg_show_progress(command, ffmpeg_loglevel="info"):
    """
    This function runs an FFmpeg command and prints the following info in addition to the FFmpeg output:
        - Percentage Progress
        - Speed
        - ETA (minutes and seconds)
    Example:
    Progress: 25% | Speed: 22.3x | ETA: 1m 33s
    How to use:
    run_ffmpeg_show_progress(["ffmpeg", "-i", "input.mp4", "-c:a", "libmp3lame", "output.mp3"])
    An optional show_ffmpeg_output paramater is available to set the value of FFmpeg's -loglevel argument.
    """

    index_of_filepath = command.index("-i") + 1
    filepath = command[index_of_filepath]

    try:
        file_duration = float(probe(filepath)["format"]["duration"])
    except Exception:
        can_get_duration = False
        print(f"\nUnable to get the duration of {filepath}:\nThe improved progress stats will not be shown.")
        show_ffmpeg_output=True
    else:
        can_get_duration = True

    process = subprocess.Popen(
        command + ["-progress", "-", "-nostats", "-loglevel", ffmpeg_loglevel],
        stdout=subprocess.PIPE,
    )

    while process.poll() is None:
        try:
            output = process.stdout.readline().decode("utf-8").strip()
        except Exception:
            pass
        else:
            if can_get_duration:
                if "out_time_ms" in output:
                    microseconds = int(output[12:])
                    secs = microseconds / 1_000_000
                    try:
                        percentage = round((secs / file_duration) * 100, 1)
                    except Exception:
                        percentage = "Unknown"

                elif "speed" in output:
                    speed = output[6:]
                    speed = 0 if " " in speed or "N/A" in speed else float(speed[:-1])
                    try:
                        eta = (file_duration - secs) / speed
                    except ZeroDivisionError:
                        eta_string = "Unknown"
                    else:
                        minutes = int(eta / 60)
                        seconds = round(eta % 60)
                        eta_string = f'{minutes}m {seconds}s'
                    finally:
                        print(f"Progress: {percentage}% | Speed: {speed}x | ETA: {eta_string}", end="\r")
            else:
                print(output)
