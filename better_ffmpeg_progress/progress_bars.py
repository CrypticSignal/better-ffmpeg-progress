import os
import subprocess
from typing import TYPE_CHECKING

from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)
from tqdm import tqdm

from .utils import parse_ffmpeg_progress_line
from .exceptions import FfmpegProcessError

if TYPE_CHECKING:
    from .better_ffmpeg_progress import FfmpegProcess


def use_rich(
    ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen
) -> None:
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
    input_filename = ffmpeg_process_instance._input_filepath.name
    log_file = ffmpeg_process_instance._ffmpeg_log_file

    with progress_bar_instance as progress_bar:
        if duration_secs:
            task_id = progress_bar.add_task(
                f"Processing '{input_filename}'",
                total=duration_secs,
            )
            update_progress = progress_bar.update

            for line_bytes in process.stdout:
                stripped_line_bytes = line_bytes.strip()
                progress_val_secs = parse_ffmpeg_progress_line(
                    stripped_line_bytes, duration_secs
                )
                if progress_val_secs is not None and task_id is not None:
                    update_progress(task_id, completed=progress_val_secs)
        else:
            print(f"Processing '{input_filename}'...")

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
                    description=f"✓ Processed '{input_filename}'",
                )
        else:
            if task_id is not None:
                progress_bar.update(task_id)

            raise FfmpegProcessError(f"FFmpeg process failed. Check '{log_file}' for details.")


def use_tqdm(
    ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen
) -> None:
    progress_bar = None
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80

    duration_secs = ffmpeg_process_instance._duration_secs
    input_filename = ffmpeg_process_instance._input_filepath.name
    log_file = ffmpeg_process_instance._ffmpeg_log_file

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
            progress_val_secs = parse_ffmpeg_progress_line(
                stripped_line_bytes, duration_secs
            )
            if progress_val_secs is not None and progress_bar is not None:
                progress_bar.n = progress_val_secs
                progress_bar.refresh()
    else:
        print(f"Processing '{input_filename}'...")

    process.wait()

    if process.returncode == 0:
        if progress_bar:
            progress_bar.n = duration_secs
            progress_bar.set_description(f"✓ Processed '{input_filename}'")
            progress_bar.close()
        else:
            print(f"✓ Processed '{input_filename}'")
    else:
        if progress_bar:
            progress_bar.close()

        raise FfmpegProcessError(f"FFmpeg process failed. Check '{log_file}' for details.")
