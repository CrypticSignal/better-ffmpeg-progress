import os
import subprocess
from typing import TYPE_CHECKING, Optional

from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)
from tqdm import tqdm

from .utils import (
    estimate_final_size_mb,
    parse_ffmpeg_progress_line,
    parse_ffmpeg_total_size_line,
    truncate_filename,
)
from .exceptions import FfmpegProcessError

if TYPE_CHECKING:
    from .better_ffmpeg_progress import FfmpegProcess

_MAX_FILENAME_LENGTH = 60


def _format_size(current_size_mb: float, estimated_size_mb: Optional[float]) -> str:
    """
    Returns e.g. "(3.25 MB / ~14.33 MB)", "(3.25 MB)" while there is no estimate yet, or ""
    if FFmpeg has not reported a size (e.g. at the start, or when the output is "-f null").
    """
    # Also hide sizes that would display as "0.00 MB", such as a container header of a few bytes.
    if round(current_size_mb, 2) <= 0:
        return ""
    if estimated_size_mb is None:
        return f"({current_size_mb:.2f} MB)"
    return f"({current_size_mb:.2f} MB / ~{estimated_size_mb:.2f} MB)"


def _with_size(text: str, current_size_mb: float, estimated_size_mb: Optional[float]) -> str:
    size = _format_size(current_size_mb, estimated_size_mb)
    return f"{text} {size}" if size else text


def _drain(process: subprocess.Popen) -> None:
    """
    Reads FFmpeg's progress output until it ends. FFmpeg writes it to a pipe, so it must be read
    even when it is not displayed: once the pipe's buffer is full, FFmpeg blocks and never exits.
    """
    if process.stdout is not None:
        for _ in process.stdout:
            pass


def use_rich(ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen) -> None:
    task_id = None
    progress_bar_instance = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(compact=True),
        refresh_per_second=2,
    )

    duration_secs = ffmpeg_process_instance._duration_secs
    input_filename = truncate_filename(
        ffmpeg_process_instance._input_filepath.name, _MAX_FILENAME_LENGTH
    )
    log_file = ffmpeg_process_instance._ffmpeg_log_file

    with progress_bar_instance as progress_bar:
        if duration_secs:
            current_size_mb = 0.0
            task_id = progress_bar.add_task(
                f"Processing {input_filename}",
                total=duration_secs,
            )
            update_progress = progress_bar.update

            for line_bytes in process.stdout:
                stripped_line_bytes = line_bytes.strip()

                size_mb = parse_ffmpeg_total_size_line(stripped_line_bytes)
                if size_mb is not None:
                    current_size_mb = size_mb
                    continue

                # FFmpeg writes total_size before out_time_us in each progress block,
                # so updating here refreshes the bar once per block with the latest size.
                progress_val_secs = parse_ffmpeg_progress_line(stripped_line_bytes, duration_secs)
                if progress_val_secs is not None and task_id is not None:
                    estimated_size_mb = estimate_final_size_mb(
                        current_size_mb, progress_val_secs, duration_secs
                    )
                    update_progress(
                        task_id,
                        completed=progress_val_secs,
                        description=_with_size(
                            f"Processing {input_filename}", current_size_mb, estimated_size_mb
                        ),
                    )
        else:
            print(f"Processing '{input_filename}'...")
            _drain(process)

        process.wait()

        if process.returncode == 0:
            if task_id is not None:
                update_progress(task_id, completed=duration_secs)
                progress_bar.columns = (
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                )
                update_progress(
                    task_id,
                    description=_with_size(
                        f"✓ Processed '{input_filename}'", current_size_mb, None
                    ),
                )
        else:
            if task_id is not None:
                progress_bar.update(task_id)

            raise FfmpegProcessError(f"FFmpeg process failed. Check '{log_file}' for details.")


def use_tqdm(ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen) -> None:
    progress_bar = None
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80

    duration_secs = ffmpeg_process_instance._duration_secs
    input_filename = truncate_filename(
        ffmpeg_process_instance._input_filepath.name, _MAX_FILENAME_LENGTH
    )
    log_file = ffmpeg_process_instance._ffmpeg_log_file

    current_size_mb = 0.0

    if duration_secs:
        progress_bar = tqdm(
            mininterval=0.5,
            total=duration_secs,
            desc=f"Processing '{input_filename}'",
            ncols=80,
            dynamic_ncols=True if width < 80 else False,
            bar_format="{desc} {bar} {percentage:.1f}% [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
        )

        for line_bytes in process.stdout:
            stripped_line_bytes = line_bytes.strip()

            size_mb = parse_ffmpeg_total_size_line(stripped_line_bytes)
            if size_mb is not None:
                current_size_mb = size_mb
                continue

            progress_val_secs = parse_ffmpeg_progress_line(stripped_line_bytes, duration_secs)
            if progress_val_secs is not None and progress_bar is not None:
                estimated_size_mb = estimate_final_size_mb(
                    current_size_mb, progress_val_secs, duration_secs
                )
                progress_bar.n = progress_val_secs
                # set_postfix_str refreshes the bar by default
                progress_bar.set_postfix_str(_format_size(current_size_mb, estimated_size_mb))
    else:
        print(f"Processing '{input_filename}'...")
        _drain(process)

    process.wait()

    if process.returncode == 0:
        if progress_bar:
            progress_bar.n = duration_secs
            progress_bar.set_description(f"✓ Processed '{input_filename}'")
            progress_bar.set_postfix_str(_format_size(current_size_mb, None))
            progress_bar.close()
        else:
            print(f"✓ Processed '{input_filename}'")
    else:
        if progress_bar:
            progress_bar.close()

        raise FfmpegProcessError(f"FFmpeg process failed. Check '{log_file}' for details.")
