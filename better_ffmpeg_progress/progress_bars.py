from __future__ import annotations

import shutil
from types import TracebackType
from typing import TYPE_CHECKING, Any, TextIO

from .utils import estimate_final_size_mb

if TYPE_CHECKING:
    from rich.progress import Progress, TaskID
    from tqdm import tqdm


def _format_size(current_size_mb: float, estimated_size_mb: float | None) -> str:
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


def _done_mark(stream: TextIO) -> str:
    """
    Returns "✓", or "OK" if the stream cannot encode it, e.g. when standard output is redirected
    on Windows, where its encoding is usually cp1252.
    """
    try:
        "✓".encode(getattr(stream, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return "OK"
    return "✓"


def _with_size(text: str, current_size_mb: float, estimated_size_mb: float | None) -> str:
    size = _format_size(current_size_mb, estimated_size_mb)
    return f"{text} {size}" if size else text


class ProgressDisplay:
    """
    Shows the progress of FFmpeg. Used as a context manager: update() is called each time FFmpeg
    reports its progress, and complete() is called if FFmpeg succeeds.
    This base class shows nothing.
    """

    def __enter__(self) -> ProgressDisplay:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def update(self, secs: float, size_mb: float) -> None:
        pass

    def complete(self, size_mb: float) -> None:
        pass


class TextDisplay(ProgressDisplay):
    """Used when the duration is unknown, so percentage progress cannot be shown."""

    def __init__(self, filename: str, stream: TextIO) -> None:
        self._filename = filename
        self._stream = stream
        self._done = _done_mark(stream)

    def __enter__(self) -> TextDisplay:
        print(f"Processing '{self._filename}'...", file=self._stream, flush=True)
        return self

    def complete(self, size_mb: float) -> None:
        print(f"{self._done} Processed '{self._filename}'", file=self._stream, flush=True)


class RichDisplay(ProgressDisplay):
    def __init__(self, filename: str, duration_secs: float, stream: TextIO) -> None:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            Progress,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )

        self._filename = filename
        self._duration_secs = duration_secs
        self._description = f"Processing '{filename}'"
        self._done = _done_mark(stream)
        self._progress_bar: Progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(compact=True),
            refresh_per_second=2,
            console=Console(file=stream),
        )
        self._task_id: TaskID | None = None

    def __enter__(self) -> RichDisplay:
        self._progress_bar.start()
        self._task_id = self._progress_bar.add_task(self._description, total=self._duration_secs)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._progress_bar.stop()

    def update(self, secs: float, size_mb: float) -> None:
        assert self._task_id is not None
        estimated_size_mb = estimate_final_size_mb(size_mb, secs, self._duration_secs)
        self._progress_bar.update(
            self._task_id,
            completed=secs,
            description=_with_size(self._description, size_mb, estimated_size_mb),
        )

    def complete(self, size_mb: float) -> None:
        assert self._task_id is not None
        # Remove the time columns, which are no longer useful.
        self._progress_bar.columns = self._progress_bar.columns[:3]
        self._progress_bar.update(
            self._task_id,
            completed=self._duration_secs,
            description=_with_size(f"{self._done} Processed '{self._filename}'", size_mb, None),
        )


class TqdmDisplay(ProgressDisplay):
    def __init__(self, filename: str, duration_secs: float, stream: TextIO) -> None:
        from tqdm import tqdm

        self._filename = filename
        self._duration_secs = duration_secs
        self._done = _done_mark(stream)
        terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns
        self._progress_bar: tqdm[Any] = tqdm(
            mininterval=0.5,
            total=duration_secs,
            desc=f"Processing '{filename}'",
            ncols=80,
            dynamic_ncols=terminal_width < 80,
            bar_format="{desc} {bar} {percentage:.1f}% [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
            file=stream,
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._progress_bar.close()

    def update(self, secs: float, size_mb: float) -> None:
        self._progress_bar.n = secs
        # set_postfix_str refreshes the bar.
        self._progress_bar.set_postfix_str(
            _format_size(size_mb, estimate_final_size_mb(size_mb, secs, self._duration_secs))
        )

    def complete(self, size_mb: float) -> None:
        self._progress_bar.n = self._duration_secs
        self._progress_bar.set_description(f"{self._done} Processed '{self._filename}'")
        self._progress_bar.set_postfix_str(_format_size(size_mb, None))


def make_display(
    filename: str,
    duration_secs: float | None,
    stream: TextIO,
    quiet: bool,
    use_tqdm: bool,
) -> ProgressDisplay:
    if quiet:
        return ProgressDisplay()
    if not duration_secs:
        return TextDisplay(filename, stream)
    if use_tqdm:
        return TqdmDisplay(filename, duration_secs, stream)
    return RichDisplay(filename, duration_secs, stream)
