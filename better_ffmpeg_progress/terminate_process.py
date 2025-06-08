import os
import psutil
import subprocess
from sys import exit
from typing import Optional

_TERMINATION_TIMEOUT = 2


def _terminate_children_processes(parent_proc: psutil.Process):
    """Helper to terminate child processes of the given parent process."""
    try:
        if not parent_proc.is_running():
            return
        children = parent_proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        print(
            f"Parent process {parent_proc.pid} not found or is a zombie while fetching children."
        )
        return
    except psutil.AccessDenied:
        print(
            f"Access denied when trying to list children of {parent_proc.pid}. Skipping child termination."
        )
        return
    except Exception as e:
        print(
            f"Error fetching children for process {parent_proc.pid}: {e}. Skipping child termination."
        )
        return

    if not children:
        return

    print(
        f"Attempting to terminate {len(children)} child process(es) of {parent_proc.pid}..."
    )
    for child in children:
        try:
            if child.is_running():
                child.terminate()
        except psutil.Error:
            pass

    _, alive = psutil.wait_procs(children, timeout=_TERMINATION_TIMEOUT)

    if alive:
        print(f"Force killing {len(alive)} remaining child process(es)...")
        for child_to_kill in alive:
            try:
                if child_to_kill.is_running():
                    child_to_kill.kill()
            except psutil.Error:
                pass


def _terminate_parent_process_windows(proc: psutil.Process):
    try:
        # Same as .kill() on Windows
        proc.terminate()
        proc.wait(timeout=_TERMINATION_TIMEOUT)
    except psutil.NoSuchProcess:
        print(f"FFmpeg process {proc.pid} already exited.")
    except psutil.TimeoutExpired:
        print(
            f"FFmpeg process {proc.pid} did not terminate within {_TERMINATION_TIMEOUT}s. Checking status..."
        )
        try:
            # Check the status after the timeout
            if proc.is_running():
                print(
                    f"FFmpeg process {proc.pid} still running after {_TERMINATION_TIMEOUT}s."
                )
            else:
                print(
                    f"FFmpeg process termination took longer than {_TERMINATION_TIMEOUT}s."
                )
        except psutil.NoSuchProcess:
            print(
                f"FFmpeg process not found after {_TERMINATION_TIMEOUT}s. It seems like it has terminated."
            )
        except psutil.Error as e:
            print(
                f"Error during status check for process {proc.pid} after timeout:\n{e}"
            )
    except psutil.AccessDenied:
        print(f"Access denied when trying to terminate FFmpeg process {proc.pid}.")
    except psutil.Error as e:
        print(f"Unable to terminate FFmpeg process:\n{e}")


def _terminate_parent_process_unix(proc: psutil.Process, original_pid: int):
    """Helper to terminate the parent process and its group on Unix operating systems."""
    from signal import SIGTERM, SIGKILL

    terminated_by_pg = False
    pgid_to_signal = 0
    try:
        pgid_to_signal = os.getpgid(original_pid)
        print(f"Sending SIGTERM to process group {pgid_to_signal}...")
        os.killpg(pgid_to_signal, SIGTERM)

        try:
            proc.wait(timeout=_TERMINATION_TIMEOUT)

            if not proc.is_running():
                terminated_by_pg = True
        except psutil.TimeoutExpired:
            print(
                f"Process group {pgid_to_signal} did not exit after SIGTERM, sending SIGKILL..."
            )
            os.killpg(pgid_to_signal, SIGKILL)
            try:
                proc.wait(
                    timeout=_TERMINATION_TIMEOUT
                )  # Wait for SIGKILL on process group
                if not proc.is_running():
                    terminated_by_pg = True
            except psutil.TimeoutExpired:
                print(f"Process group {pgid_to_signal} still running after SIGKILL.")
            # Process died after SIGKILL
            except psutil.NoSuchProcess:
                terminated_by_pg = True
        # Process died after SIGTERM
        except psutil.NoSuchProcess:
            terminated_by_pg = True
    # os.getpgid(original_pid) failed
    except ProcessLookupError:
        print(
            f"ProcessLookupError for PID {original_pid} when trying to get PGID. Fallback to individual process."
        )
    # os.killpg failed
    except OSError as e:
        target_desc = (
            f"process group {pgid_to_signal}"
            if pgid_to_signal != 0
            else f"process {original_pid}"
        )
        print(
            f"Error sending signal to {target_desc}: {e}. Fallback to individual process."
        )

    if terminated_by_pg:
        return

    # Fallback: Terminate the main process directly if process group termination failed or was skipped
    try:
        if proc.is_running():
            print(f"Attempting direct SIGTERM for main process {proc.pid}...")
            try:
                # Send SIGTERM
                proc.terminate()
                proc.wait(timeout=_TERMINATION_TIMEOUT)
                # Successfully terminated with SIGTERM
                if not proc.is_running():
                    return
            except psutil.TimeoutExpired:
                print(
                    f"SIGTERM for FFmpeg process (PID: {proc.pid}) timed out after {_TERMINATION_TIMEOUT}s."
                )
            except psutil.Error as e:
                print(
                    f"Error during SIGTERM for FFmpeg process (PID: {proc.pid}):\n{e}"
                )
                if not proc.is_running():
                    return

            # If SIGTERM failed/timed out and the process is still running, try SIGKILL:

            # Check if process is still running
            if proc.is_running():
                print(
                    f"FFmpeg process (PID: {proc.pid}) still running after direct SIGTERM, attempting SIGKILL..."
                )
                try:
                    # Send SIGKILL
                    proc.kill()
                    print(f"SIGKILL sent to FFmpeg process (PID: {proc.pid}).")
                except psutil.Error as e:
                    print(
                        f"Error during SIGKILL for FFmpeg process (PID: {proc.pid}):\n{e}"
                    )
        else:
            print(f"It seems like FFmpeg process {proc.pid} is no longer running.")
    except psutil.NoSuchProcess:
        print(f"It seems like the FFmpeg process (PID: {proc.pid}) has terminated.")
    except psutil.Error as e:
        print(f"Unable to check the status of FFmpeg process (PID: {proc.pid}):\n{e}")


def terminate_ffmpeg_process(process: Optional[subprocess.Popen]):
    """
    Terminates an FFmpeg process and its children.
    'process' is the subprocess.Popen object for the FFmpeg process.
    """
    if not process or process.poll() is not None:
        return

    original_pid = process.pid

    parent_ps_proc: Optional[psutil.Process] = None
    try:
        parent_ps_proc = psutil.Process(original_pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        print(
            f"FFmpeg process {original_pid} already gone or is a zombie when termination started."
        )
        return
    except Exception as e:
        print(f"Error accessing FFmpeg process {original_pid} with psutil: {e}")
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=_TERMINATION_TIMEOUT)
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=_TERMINATION_TIMEOUT)
            except Exception as popen_term_err:
                print(f"Error during fallback Popen termination: {popen_term_err}")
        return

    print("[better-ffmpeg-progress] Terminating the FFmpeg process...")

    if parent_ps_proc:
        _terminate_children_processes(parent_ps_proc)

    try:
        if parent_ps_proc and parent_ps_proc.is_running():
            if os.name == "nt":
                _terminate_parent_process_windows(parent_ps_proc)
            else:
                _terminate_parent_process_unix(parent_ps_proc, original_pid)
        elif parent_ps_proc:
            print(
                f"Main FFmpeg process {parent_ps_proc.pid} exited, possibly during child termination or was already gone."
            )
    except psutil.NoSuchProcess:
        print(
            f"Main FFmpeg process {original_pid} became inaccessible during termination sequence."
        )
    except Exception as e:
        print(
            f"Unexpected error during main process termination for {original_pid}: {e}"
        )

    if process.poll() is None:
        exit("It seems like the FFmpeg process has not terminated.")
    else:
        print(f"FFmpeg process (PID: {original_pid}) terminated.")
