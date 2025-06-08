class FfmpegProcessError(Exception):
    pass


class FfmpegCommandError(FfmpegProcessError):
    pass


class FfmpegProcessUserCancelledError(FfmpegProcessError):
    pass


class FfmpegProcessInterruptedError(FfmpegProcessError):
    pass
