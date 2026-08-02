import os
import subprocess
from typing import TYPE_CHECKING
from rich.console import Console
from rich.theme import Theme
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


def truncate_filename(filename: str, max_length: int = 60) -> str:
    """Truncates a filename if it exceeds max_length while preserving the file extension."""
    if len(filename) <= max_length:
        return filename

    stem, ext = os.path.splitext(filename)
    ellipsis = "..."
    allowed_stem_len = max_length - len(ext) - len(ellipsis)

    if allowed_stem_len < 1:
        return filename[: max_length - len(ellipsis)] + ellipsis

    return f"{stem[:allowed_stem_len]}{ellipsis}{ext}"

custom_theme = Theme({
    "progress.elapsed": "bold white",
    "progress.remaining": "white",
    "progress.percentage": "sea_green3",
})

console = Console(theme=custom_theme)

def use_rich(ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen) -> None:
    task_id = None
    progress_bar_instance = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, style="grey15", complete_style="bold sea_green3", finished_style="bold bright_green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(compact=True),
        refresh_per_second=8,
        console=console,
    )

    duration_secs = ffmpeg_process_instance._duration_secs
    input_filename = truncate_filename(ffmpeg_process_instance._input_filepath.name, max_length=60)
    log_file = ffmpeg_process_instance._ffmpeg_log_file

    with progress_bar_instance as progress_bar:
        if duration_secs:
            current_size_mb = 0.0
            current_time_secs = 0.0
            estimated_size_mb = 0.0

            # Line 1: Header/Filename printed separately
            console.print(f"Processing {input_filename}")

            # Line 2: Progress metrics and size stats
            task_id = progress_bar.add_task(
                " (0.00 MB / ~0.00 MB)",
                total=duration_secs,
            )
            update_progress = progress_bar.update

            for line_bytes in process.stdout:
                stripped_line_bytes = line_bytes.strip()
                progress_data = parse_ffmpeg_progress_line(stripped_line_bytes, duration_secs)

                if progress_data and task_id is not None:
                    if "size_mb" in progress_data:
                        current_size_mb = progress_data["size_mb"]

                    if "time_secs" in progress_data:
                        current_time_secs = progress_data["time_secs"]

                    # Calculate dynamic estimated final size
                    if current_time_secs > 0:
                        estimated_size_mb = (current_size_mb / current_time_secs) * duration_secs

                    update_progress(
                        task_id,
                        completed=current_time_secs,
                        description=f" ({current_size_mb:.2f} MB / ~{estimated_size_mb:.2f} MB)",
                    )
        else:
            print(f"Processing '{input_filename}'...")

        process.wait()

        if process.returncode == 0:
            if task_id is not None:
                update_progress(task_id, completed=duration_secs)
                progress_bar.columns = (
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(bar_width=40, style="red", complete_style="green", finished_style="bold bright_green"),
                    TaskProgressColumn(),
                )
                update_progress(
                    task_id,
                    description=f"✓ Final Size: {current_size_mb:.2f} MB",
                )

def use_tqdm(ffmpeg_process_instance: "FfmpegProcess", process: subprocess.Popen) -> None:
    progress_bar = None
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80

    duration_secs = ffmpeg_process_instance._duration_secs
    # Truncate input filename to a max of 60 characters
    input_filename = truncate_filename(ffmpeg_process_instance._input_filepath.name, max_length=60)
    log_file = ffmpeg_process_instance._ffmpeg_log_file

    if duration_secs:
        current_size_mb = 0.0
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
            progress_data = parse_ffmpeg_progress_line(stripped_line_bytes, duration_secs)

            if progress_data and progress_bar is not None:
                if "size_mb" in progress_data:
                    current_size_mb = progress_data["size_mb"]
                    progress_bar.set_postfix_str(f"{current_size_mb:.2f} MB")

                if "time_secs" in progress_data:
                    progress_bar.n = progress_data["time_secs"]
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