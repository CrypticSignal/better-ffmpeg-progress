import abc
import inspect
import shlex
import subprocess
import sys
import tempfile
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

# TODO use `rich` instead of `tqdm`
from tqdm import tqdm


def getattr_from_instance(f: Callable):
    @wraps(f)
    def wrapper(self=None, *args, **kwargs):
        def getattr_without_Base(self, name):
            # None while function from class which endswith 'Base'

            attr = getattr(self, name)
            if inspect.isfunction(attr):
                attr_class_name = attr.__qualname__.partition(".")[0]
                if attr_class_name.endswith("Base"):
                    return None
            return attr

        if self is None:
            return f(self, *args, **kwargs)

        names = inspect.getfullargspec(f).args[1:]

        names.reverse()
        for arg in args:
            if arg is not None:
                names.pop()

        names = set(names)
        for key, arg in kwargs.items():
            if arg is not None:
                names.remove(key)

        instance_vars = {name: getattr_without_Base(self, name) for name in names}

        return f(self, *args, **kwargs, **instance_vars)

    return wrapper


class FfmpegProcessBase(abc.ABC):
    ffmpeg_output_file: Optional["str | Path"] = None

    def __init__(self, commands: "str | list[str]", ffmpeg_loglevel="verbose", hide_tips=False):
        ...

    @abc.abstractmethod
    def run(
        self,
        progress_handler: Optional[
            Callable[[float, float, Optional[float], Optional[float]], None]
        ] = None,
        ffmpeg_output_file: Optional["str | Path"] = None,
        success_handler: Optional[Callable] = None,
        error_handler: Optional[Callable] = None,
    ):
        ...

    @staticmethod
    def progress_handler(
        percentage: float, speed: float, eta: Optional[float], estimated_size: Optional[float]
    ):
        ...

    @staticmethod
    def success_handler():
        ...

    @staticmethod
    def error_handler():
        ...


class FfmpegProcess(FfmpegProcessBase):
    """
    Args:
        command (list): A list of arguments to pass to FFmpeg.

        ffmpeg_loglevel (str, optional): Desired FFmpeg log level. Default is "verbose".

        hide_tips (bool, optional): Hide tips from `FfmpegProcess`.

    Raises:
        ValueError: If the list of arguments does not include "-i".
    """

    def __init__(self, commands, ffmpeg_loglevel="verbose", hide_tips=False):
        self.print: Callable[..., None] = (lambda *msg, **kw: None) if hide_tips else print

        if isinstance(commands, str):
            commands = shlex.split(commands)

        if "-i" not in commands:
            raise ValueError("FFmpeg command must include '-i'")

        # TODO get correct name if file_name is not the last argument
        self._output_filepath = commands[-1]

        if "-hide_banner" not in commands:
            commands.append("-hide_banner")
        if "-loglevel" not in commands:
            commands.extend(["-loglevel", ffmpeg_loglevel])

        self._ffmpeg_args = commands

        # info init
        self._estimated_size: Optional[float] = None
        self._eta: Optional[float] = None
        self._percentage = 0.0
        self._progress_bar: Optional[tqdm] = None
        self._seconds_processed = 0.0
        self._speed = 0.0
        self._current_size = 0.0
        self._duration_secs = 0.0

        self._set_file_info()

        if self.__class__ != FfmpegProcess:
            self.run()

    def _get_duration(self, file_path):
        try:
            process = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    "-i",
                    file_path,
                ],
                capture_output=True,
                check=True,
            )

        except subprocess.CalledProcessError:
            self._can_get_duration = False
            return False

        else:
            self.print(
                f"The duration of {file_path} has been "
                f"detected as {float(process.stdout)} seconds."
            )
            self._duration_secs += float(process.stdout)

            self._can_get_duration = True
            return True

    def _set_file_info(self):
        # TODO support multiple input files
        index_of_filepath = self._ffmpeg_args.index("-i") + 1
        self._file_path = self._ffmpeg_args[index_of_filepath]

        self._get_duration(self._file_path)

        if self._can_get_duration:
            self._ffmpeg_args += ["-progress", "pipe:1", "-nostats"]

    def _should_overwrite(self):
        if "-y" not in self._ffmpeg_args and Path(self._output_filepath).exists():
            choice = input(f"{self._output_filepath} already exists. Overwrite? [Y/N]: ")

            if choice.lower() != "y":
                self.print(
                    "FFmpeg will not run as the output filename already exists, "
                    "and you do not want it to be overwritten."
                )
                return False

            self._ffmpeg_args.insert(1, "-y")
        return True

    def _update_progress(
        self,
        ffmpeg_output: str,
        progress_handler: Optional[
            Callable[[float, float, Optional[float], Optional[float]], None]
        ],
    ):
        if not ffmpeg_output:
            return
        value = ffmpeg_output.partition("=")[-1].strip()

        if progress_handler is None:
            if ffmpeg_output.startswith("out_time_ms"):
                seconds_processed = float(value) / 1_000_000
                if self._progress_bar:
                    self._progress_bar.update(int(seconds_processed - self._progress_bar.n))
            return

        # handle while `progress=continue` or `progress=end`
        if ffmpeg_output.startswith("progress"):
            if ffmpeg_output == "progress=end":
                self._percentage = 100
                self._eta = 0
                if self._progress_bar:
                    self._progress_bar.update(int(self._duration_secs - self._progress_bar.n))

            progress_handler(self._percentage, self._speed, self._eta, self._estimated_size)

        elif ffmpeg_output.startswith("total_size") and "N/A" not in value:
            self._current_size = float(value)

        elif ffmpeg_output.startswith("out_time_ms"):
            self._seconds_processed = float(value) / 1_000_000

            if self._can_get_duration:
                self._percentage = (self._seconds_processed / self._duration_secs) * 100

                if self._current_size is not None and self._percentage != 0.0:
                    self._estimated_size = self._current_size * (100 / self._percentage)

        elif ffmpeg_output.startswith("speed"):
            speed_str = value.rstrip("x")  # rstrip `22.3x` to `22.3`, and preserve `N/A`

            if speed_str != "0" and "N/A" not in speed_str:
                self._speed = float(speed_str)

                if self._can_get_duration:
                    self._eta = (self._duration_secs - self._seconds_processed) / self._speed

    @getattr_from_instance
    def run(
        self,
        progress_handler,
        ffmpeg_output_file,
        success_handler,
        error_handler,
    ):
        if not self._should_overwrite():
            return
        if ffmpeg_output_file is None:
            ffmpeg_output_path = Path(tempfile.gettempdir()) / "ffmpeg_output"
            ffmpeg_output_path.mkdir(exist_ok=True)
            ffmpeg_output_file = ffmpeg_output_path / f"{Path(self._file_path).name}.txt"

        self.print(f"\nRunning: {' '.join(self._ffmpeg_args)}\n")

        if progress_handler is None and self._can_get_duration:
            self._progress_bar = tqdm(
                total=int(self._duration_secs),
                unit="s",
                dynamic_ncols=True,
                leave=False,
            )

        with open(ffmpeg_output_file, "a") as f:
            process = subprocess.Popen(self._ffmpeg_args, stdout=subprocess.PIPE, stderr=f)

        try:
            while process.poll() is None:
                ffmpeg_out_io = process.stdout
                if ffmpeg_out_io is None:
                    continue

                # iter file_io will call file_io.readline()
                for ffmpeg_output in ffmpeg_out_io:
                    self._update_progress(ffmpeg_output.decode().strip(), progress_handler)

            if process.returncode != 0:
                if error_handler:
                    error_handler()

                self.print(
                    "\nThe FFmpeg process encountered an error. "
                    f"The output of FFmpeg can be found in {ffmpeg_output_file}"
                )
                return

            if success_handler:
                success_handler()

            self.print(f"\n\nDone! To see FFmpeg's output, check out {ffmpeg_output_file}")

        except KeyboardInterrupt:
            if self._progress_bar:
                self._progress_bar.close()
            process.terminate()
            self.print("[KeyboardInterrupt] FFmpeg process killed.")
            sys.exit()

        except Exception as e:
            self.print(f"[Better FFmpeg Process] {e}")


def ffmpeg_process(
    commands: "str | list[str]",
    ffmpeg_loglevel="verbose",
    hide_tips=False,
    progress_handler: Optional[
        Callable[[float, float, Optional[float], Optional[float]], None]
    ] = None,
    ffmpeg_output_file: Optional["str | Path"] = None,
    success_handler: Optional[Callable] = None,
    error_handler: Optional[Callable] = None,
):
    FfmpegProcess(commands, ffmpeg_loglevel, hide_tips).run(
        progress_handler, ffmpeg_output_file, success_handler, error_handler
    )
