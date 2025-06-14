[19/09/2022]
- Add the ability to specify a `success_handler` argument, a function to run if the FFmpeg process completes successfully.
- Add 0.001 to tqdm's `total` parameter to prevent the chance of getting `TqdmWarning: clamping frac to range [0, 1]`

[21/12/2022]
- [v2.0.7] Fix `'estimated_size' referenced before assignment` error.
- [v2.0.7] The progress bar now uses 1 decimal place for seconds processed and total duration.

[22/12/2022]
- [v2.0.8] Add the ability to specify an `error_handler` argument, a function to run if the FFmpeg process encounters an error.
- [v2.0.9] Fix a typo (commit [da45a84](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/da45a8416856ab7d3c7b748db5703fa3dbc65f60))

[07/02/2022]
- [v2.1.0] [Update function name](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/572fe8a0d71957d00b833134a4d35170630203fa) to fix `'process_complete_handler' is not defined` error.

[05/11/2023]
- [v2.1.2] [Do not exit the Python interpreter after the FFmpeg process is complete](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/0a358810773835297faae688689c6e0d8a5859ae)

[22/04/2024]
- [v2.1.3] Fix issue [#20](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/20)

[28/04/2024]
- [v2.1.4] Fix issue [#21](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/21)

[02/05/2024]
- [v2.1.5] Fix issue [#23](https://github.com/CrypticSignal/better-ffmpeg-progress/issues/23) and make an error message more specific. [Here](https://github.com/CrypticSignal/better-ffmpeg-progress/commit/a6ef7f26d080b684144021301f3b2aa5e0834dae) is the relevant commit.

[18/10/2024]
- [v2.1.6] Notify the user if the input filepath or filename is incorrect.
- [v2.1.7] Refactor to use threads and queues.

[19/10/2024]
- [v2.1.8] Use [Rich](https://github.com/Textualize/rich) instead of [tqdm](https://github.com/tqdm/tqdm) and format code with [Ruff](https://github.com/astral-sh/ruff).

[20/10/2024]
- [v2.1.9] Do not clear the terminal before showing the progress bar.
- [v2.2.0] Add the ability to set a custom description for the progress bar.

[22/10/2024]
- [v2.2.1] Only create a log file if the `log_file` parameter is specified and always create a log file if the FFmpeg process fails.

[28/10/2024]
- [v2.2.2] Make printing the detected duration of the input file optional.

[29/10/2024]
- [v2.3.0] Set `shell=True` to support piping.
- [v2.3.1] Kill FFmpeg process(es) on KeyboardInterrupt

[31/10/2024]
- [v2.4.0] Print FFmpeg stderr if better progress information cannot be shown.
- [v2.4.0] Flush the stream when printing FFmpeg stderr to ensure that it is printed immediately.
- [v2.5.0] Add an option to print FFmpeg stderr on a new line if better progress information cannot be shown.

[11/11/2024]
- [v2.5.1] Print the correct log file.

[12/11/2024]
- [v2.5.2] Drain any remaining FFmpeg stderr after the process ends.
- [v2.5.3] Write FFmpeg stderr to the log file in real time.
- [v2.5.4] Include progress info in stderr if the duration of the input file cannot be detected.
- [v2.5.5] Print detected errors in the terminal and only set `shell=True` if shell operators are detected.

[13/11/2024]
- [v2.5.6] Detect a wider range of errors.

[18/11/2024]
- [v2.5.7] Fix syntax. Should fix issue #26

[19/11/2024]
- [v2.5.8] Remove `\n` from replacement fields in f-strings. Should fix issue #26

[25/12/2024]
- [v2.6.0] Make printing the FFmpeg command being executed optional, remove progress bar on successful process completion and instead show `✓ Processed 100% of <input filename>`
- [v2.6.1] Disable duration printing by default and fix overwrite functionality.

[27/12/2024]
- [v3.0.0] [Refactor] Handle process success/failure through a return code instead of supplying success/error handler functions. Remove the ability to provide a custom progress handler.
- [v3.1.0] Inform the user that they can check out the log file if the FFmpeg process did not complete successfully.

[18/02/2025]
- [v3.2.0] 
    - Support using [tqdm](https://github.com/tqdm/tqdm) instead of [Rich](https://github.com/Textualize/rich).
    - Rich is used by default.
    - Keep the progress bar and percentage progress upon completion.

[23/02/2025]
- [v3.2.1] 
    - Leave FFmpeg encoding progress/statistics update frequency as the default of 2 times per second, instead of 10 times per second.
    - Add a 0.5 seconds sleep at the start of the `while process.poll() is None` loop to eliminate unnecessary iterations of this loop.
    - Use `Queue.get()` instead of `Queue.get_nowait()`. Non-blocking queue item retrieval is not needed due to the `not stdout_queue.empty()` and `not stderr_queue.empty()` checks. Because of these checks, `get()` will never block as we only run this code if the queue is not empty. Refer to issue #29 for context.

[26/02/2025]
- [v3.2.2] No longer create threads to read FFmpeg stdout and stderr.

[27/02/2025]
- [v3.2.3]
    - No longer require ffmpeg-python, use ffprobe directly.
    - Performance optimisations.
- [v3.2.4]
    - Fix AttributeError.
- [v3.2.5]
    - Fix issue #30
- [v3.2.6]
    - Simplify the `_should_overwrite` method.
    - Refactor the `_terminate` method.

[08/06/2025]
- [v4.0.0] 
    - Make `return_code` a property of `FfmpegProcess`
    - Make `use_tqdm` a property of `FfmpegProcess`
    - Create new files to separate some methods for easier maintainability.
    - Add a file (test.py) for testing.

[10/06/2025]
- [v4.0.1] Add `"requests"` to `install_requires`