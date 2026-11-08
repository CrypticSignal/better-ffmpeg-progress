import os
import subprocess
from typing import Optional

from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from tqdm import tqdm

from .utils import estimate_final_size_mb, read_progress


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


def show_rich_progress(process: subprocess.Popen, filename: str, duration_secs: float) -> None:
    """Shows a Rich progress bar until FFmpeg exits."""
    description = f"Processing '{filename}'"
    progress_bar = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(compact=True),
        refresh_per_second=2,
    )

    with progress_bar:
        task_id = progress_bar.add_task(description, total=duration_secs)
        size_mb = 0.0

        for secs, size_mb in read_progress(process.stdout, duration_secs):
            estimated_size_mb = estimate_final_size_mb(size_mb, secs, duration_secs)
            progress_bar.update(
                task_id,
                completed=secs,
                description=_with_size(description, size_mb, estimated_size_mb),
            )

        if process.wait() == 0:
            # Remove the time columns, which are no longer useful.
            progress_bar.columns = progress_bar.columns[:3]
            progress_bar.update(
                task_id,
                completed=duration_secs,
                description=_with_size(f"✓ Processed '{filename}'", size_mb, None),
            )


def show_tqdm_progress(process: subprocess.Popen, filename: str, duration_secs: float) -> None:
    """Shows a tqdm progress bar until FFmpeg exits."""
    try:
        terminal_width = os.get_terminal_size().columns
    except OSError:
        terminal_width = 80

    progress_bar = tqdm(
        mininterval=0.5,
        total=duration_secs,
        desc=f"Processing '{filename}'",
        ncols=80,
        dynamic_ncols=terminal_width < 80,
        bar_format="{desc} {bar} {percentage:.1f}% [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
    )
    size_mb = 0.0

    with progress_bar:
        for secs, size_mb in read_progress(process.stdout, duration_secs):
            progress_bar.n = secs
            # set_postfix_str refreshes the bar.
            progress_bar.set_postfix_str(
                _format_size(size_mb, estimate_final_size_mb(size_mb, secs, duration_secs))
            )

        if process.wait() == 0:
            progress_bar.n = duration_secs
            progress_bar.set_description(f"✓ Processed '{filename}'")
            progress_bar.set_postfix_str(_format_size(size_mb, None))
