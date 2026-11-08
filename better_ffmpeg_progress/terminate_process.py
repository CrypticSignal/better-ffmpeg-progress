import os
import signal
import subprocess

from .exceptions import FfmpegProcessError
from .utils import logger

# How long FFmpeg is given to finish writing the output file after being asked to stop.
_GRACEFUL_TIMEOUT_SECS = 5
_TIMEOUT_SECS = 2


def _signal_process_group(process: subprocess.Popen[bytes], sig: int) -> None:
    # FFmpeg is started in its own process group (see FfmpegProcess.run), whose ID is FFmpeg's PID.
    # Signalling the group also stops any processes that FFmpeg started.
    try:
        os.killpg(process.pid, sig)  # type: ignore[attr-defined,unused-ignore]
    except ProcessLookupError:
        pass  # The process has already exited.


def _ask_to_quit(process: subprocess.Popen[bytes]) -> bool:
    """
    Sends "q" to FFmpeg's standard input, which makes FFmpeg stop and finish writing the output
    file, so the file is playable. Returns True if FFmpeg exited in time.
    """
    if process.stdin is None:
        return False
    try:
        process.stdin.write(b"q")
        process.stdin.flush()
    except OSError:  # e.g. BrokenPipeError if FFmpeg has just exited.
        pass
    try:
        process.wait(timeout=_GRACEFUL_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        return False
    return True


def terminate_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    """
    Stops the FFmpeg process, gracefully if possible. Raises FfmpegProcessError if it is still
    running afterwards.
    """
    if process.poll() is not None:
        return

    logger.info("Stopping the FFmpeg process...")

    if _ask_to_quit(process):
        return

    if os.name == "nt":
        # On Windows, terminate() stops the process immediately.
        process.terminate()
    else:
        # Ask FFmpeg to exit, and force it to if it has not done so in time.
        _signal_process_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)  # type: ignore[attr-defined,unused-ignore]

    try:
        process.wait(timeout=_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        raise FfmpegProcessError(
            f"FFmpeg process (PID: {process.pid}) could not be terminated."
        ) from None
