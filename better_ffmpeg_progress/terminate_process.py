import os
import signal
import subprocess

from .exceptions import FfmpegProcessError

_TIMEOUT_SECS = 2


def _signal_process_group(process: subprocess.Popen, sig: int) -> None:
    # FFmpeg is started in its own process group (see FfmpegProcess.run), whose ID is FFmpeg's PID.
    # Signalling the group also stops any processes that FFmpeg started.
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass  # The process has already exited.


def terminate_ffmpeg_process(process: subprocess.Popen) -> None:
    """
    Stops the FFmpeg process. Raises FfmpegProcessError if it is still running afterwards.
    """
    if process.poll() is not None:
        return

    print("[KeyboardInterrupt] Terminating the FFmpeg process...")

    if os.name == "nt":
        # On Windows, terminate() stops the process immediately.
        process.terminate()
    else:
        # Ask FFmpeg to exit, and force it to if it has not done so in time.
        _signal_process_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)

    try:
        process.wait(timeout=_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        raise FfmpegProcessError(
            f"FFmpeg process (PID: {process.pid}) could not be terminated."
        ) from None
