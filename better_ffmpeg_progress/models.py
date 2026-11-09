from __future__ import annotations

import os
from dataclasses import dataclass
from typing import IO, Any


@dataclass(frozen=True)
class FfmpegProgress:
    """
    A progress report from FFmpeg, passed to the on_progress function of FfmpegProcess.

    Attributes:
        secs: Seconds of the output processed so far.
        duration_secs: The expected duration of the output in seconds, or None if it is unknown.
        size_mb: The current size of the output in MB.
        speed: How fast FFmpeg is processing compared to real time (e.g. 2.5 means 2.5x), or
            None if FFmpeg has not reported it yet.
        fps: Frames processed per second, or None if there is no video or it is not reported yet.
        frame: The number of frames processed, or None if there is no video.
        bitrate_kbps: The output bitrate in kbit/s, or None if it is not reported yet.
    """

    secs: float
    duration_secs: float | None
    size_mb: float
    speed: float | None = None
    fps: float | None = None
    frame: int | None = None
    bitrate_kbps: float | None = None

    @property
    def percentage(self) -> float | None:
        """The progress as a percentage from 0 to 100, or None if the duration is unknown."""
        if not self.duration_secs:
            return None
        return min(self.secs / self.duration_secs * 100, 100.0)


@dataclass(frozen=True)
class FfmpegResult:
    """
    Returned by FfmpegProcess.run() when FFmpeg succeeds.

    Attributes:
        elapsed_secs: How long FFmpeg ran for, in seconds.
        processed_secs: Seconds of the output processed, as last reported by FFmpeg.
        duration_secs: The expected duration of the output in seconds that was used for the
            progress bar, or None if it was unknown.
        output_size_mb: The size of the output in MB, as last reported by FFmpeg.
        log_file: The path or file object that FFmpeg's log was written to. It no longer exists
            if delete_log_on_success was used.
    """

    elapsed_secs: float
    processed_secs: float
    duration_secs: float | None
    output_size_mb: float
    log_file: str | os.PathLike[str] | IO[Any]
