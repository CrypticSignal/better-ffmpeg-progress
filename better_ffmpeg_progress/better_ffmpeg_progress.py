import abc
import inspect
import shlex
import subprocess
import sys
import tempfile
from functools import wraps
from pathlib import Path
from typing import Callable, Optional, ClassVar
from collections import defaultdict

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

        # use list.pop to get O(1) speed
        args_list = list(reversed(args))
        names.reverse()

        for arg in args:
            if arg is None:
                args_list.pop()
            else:
                names.pop()

        args_list.reverse()

        # use set.remove to get O(1) speed
        names_set = set(names)
        for key, arg in kwargs.items():
            if arg is not None:
                names_set.remove(key)

        instance_vars = {name: getattr_without_Base(self, name) for name in names_set}
        return f(self, *args_list, **kwargs, **instance_vars)

    return wrapper


def raise_error(*args, error: Optional["type[Exception]"] = None, **kwargs):
    if error:
        raise error(*args, **kwargs)


def print_without_error(*args, error: Optional["type[Exception]"] = None, **kwargs):
    print(*args, **kwargs)


class FfmpegProcessBase(abc.ABC):
    ffmpeg_output_file: ClassVar[Optional["str | Path"]] = None

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
                    If the output_file_path can not get

        RuntimeError: If hide_tips == True and the FFmpeg process encountered an error.
    """

    def __init__(self, commands, ffmpeg_loglevel="verbose", hide_tips=False):
        self.print: Callable[..., None] = raise_error if hide_tips else print_without_error

        if isinstance(commands, str):
            commands = shlex.split(commands, posix=False)

        if "-i" not in commands:
            raise ValueError("FFmpeg command must include '-i'")

        if "-hide_banner" not in commands:
            commands.append("-hide_banner")
        if "-loglevel" not in commands:
            commands.extend(["-loglevel", ffmpeg_loglevel])

        # info init
        self._can_get_duration = True
        self._estimated_size: Optional[float] = None
        self._eta: Optional[float] = None
        self._percentage = 0.0
        self._seconds_processed = 0.0
        self._speed = 0.0
        self._current_size = 0.0
        self._duration_secs = 0.0

        self._set_file_info(commands)
        if self.__class__ != FfmpegProcess:
            self.run()

    def _set_duration(self, file_path):
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

        else:
            self.print(
                f"The duration of {file_path} has been "
                f"detected as {float(process.stdout)} seconds."
            )
            self._duration_secs += float(process.stdout)

    @staticmethod
    def _parse_commands(commands: "list[str]"):
        args: defaultdict[str, "list[str]"] = defaultdict(list)
        out_file_path = None

        option_key = ""
        for command in commands:
            # skip options without arguments
            if command in [
                # Global
                "-ignore_unknown",
                "-report",
                "-stats",
                "-nostats",
                # Advanced global
                "-hide_banner",
                "-copy_unknown",
                # Video
                "-vn",
                "-dn",
                # Audio
                "-an",
                # Subtitle
                "-sn",
            ]:
                continue

            if command.startswith("-"):
                if command in ["-y", "-n"]:
                    args[command]
                else:
                    option_key = command

                continue

            if option_key:
                if option_key in ["-i", "-f", "-ss", "-to", "-t"]:
                    args[option_key].append(command)
                option_key = ""

            else:
                args[""].append(command)

        return args

    def _iter_if_concat(self):
        _inputs = self._parse_args["-i"]
        if self._parse_args["-f"] != ["concat"]:
            yield from _inputs
            return
        for _input_file in _inputs:
            with open(_input_file) as f:
                for line in f:  # "file 'name.mp4'"
                    line_parts = line.partition("'")  # ("file", "'", "name.mp4'")
                    if line_parts[-1]:
                        yield line_parts[-1].partition("'")[0]  # ("name.mp4", "'", "")

    def _set_file_info(self, commands: "list[str]"):
        self._parse_args = self._parse_commands(commands[1:])

        if self._parse_args[""] == []:
            raise ValueError("can't not get output_file_path")
        out_file_path = self._parse_args[""][-1]

        self._ffmpeg_args = commands

        self._out_file_path = out_file_path

        for file_path in self._iter_if_concat():
            self._set_duration(file_path)
            if not self._can_get_duration:
                break

        if self._can_get_duration:
            self._ffmpeg_args += ["-progress", "pipe:1", "-nostats"]

    def _can_overwrite(self):
        if "-y" not in self._parse_args and Path(self._out_file_path).exists():
            if "-n" in self._parse_args:
                self.print(
                    "FFmpeg will not run as the output filename already exists, "
                    "and you set '-n' and do not want it to be overwritten.",
                    error=FileExistsError,
                )
                return False

            choice = input(f"{self._out_file_path} already exists. Overwrite? [Y/N]: ")

            if choice.lower() != "y":
                self.print(
                    "FFmpeg will not run as the output filename already exists, "
                    "and you do not want it to be overwritten.",
                    error=FileExistsError,
                )
                return False

            self._ffmpeg_args.append("-y")
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
                self._progress_bar.update(int(seconds_processed - self._progress_bar.n))
            return

        if ffmpeg_output.startswith("total_size") and "N/A" not in value:
            self._current_size = float(value)

        elif ffmpeg_output.startswith("out_time_ms"):
            self._seconds_processed = float(value) / 1_000_000

            self._percentage = (self._seconds_processed / self._duration_secs) * 100

            if self._current_size is not None and self._percentage != 0.0:
                self._estimated_size = self._current_size * (100 / self._percentage)

        elif ffmpeg_output.startswith("speed"):
            speed_str = value.rstrip("x")  # rstrip `22.3x` to `22.3`, and preserve `N/A`

            if speed_str != "0" and "N/A" not in speed_str:
                self._speed = float(speed_str)
                self._eta = (self._duration_secs - self._seconds_processed) / self._speed

        # handle while `progress=continue` or `progress=end`
        elif ffmpeg_output.startswith("progress"):
            if ffmpeg_output == "progress=end":
                self._percentage = 100
                self._eta = 0
                self._progress_bar.update(int(self._duration_secs - self._progress_bar.n))

            progress_handler(self._percentage, self._speed, self._eta, self._estimated_size)

    @getattr_from_instance
    def run(
        self,
        progress_handler,
        ffmpeg_output_file,
        success_handler,
        error_handler,
    ):
        if not self._can_overwrite():
            return
        if ffmpeg_output_file is None:
            ffmpeg_output_path = Path(tempfile.gettempdir()) / "ffmpeg_output"
            ffmpeg_output_path.mkdir(exist_ok=True)
            ffmpeg_output_file = ffmpeg_output_path / f"{Path(self._out_file_path).name}.txt"

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

        # raise RuntimeError when hide_tips == True and process.returncode != 0
        try:
            while process.poll() is None:
                if not self._can_get_duration:
                    continue

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
                    f"The output of FFmpeg can be found in {ffmpeg_output_file}",
                    error=RuntimeError,
                )
                return

            if success_handler:
                success_handler()

            self.print(f"\n\nDone! To see FFmpeg's output, check out {ffmpeg_output_file}")

        except KeyboardInterrupt:
            if self._can_get_duration:
                self._progress_bar.close()
            process.terminate()
            self.print("[KeyboardInterrupt] FFmpeg process killed.")
            sys.exit()


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
