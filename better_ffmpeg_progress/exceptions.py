from __future__ import annotations

import os
from typing import IO, Any


class FfmpegProcessError(Exception):
    """
    Base class for the errors raised by this package.

    Attributes:
        returncode: FFmpeg's exit code, or None if FFmpeg was not started or had not exited.
        log_file: The path or file object FFmpeg's log was written to, or None if FFmpeg was
            not started.
    """

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        log_file: str | os.PathLike[str] | IO[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.log_file = log_file


class FfmpegCommandError(FfmpegProcessError):
    pass


class FfmpegProcessUserCancelledError(FfmpegProcessError):
    pass


class FfmpegProcessInterruptedError(FfmpegProcessError):
    pass
