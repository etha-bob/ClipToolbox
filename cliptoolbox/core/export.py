import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Protocol

from cliptoolbox.constants import (
    COMPRESSION_BUDGET_EPSILON_MB,
    COMPRESSION_MAX_ATTEMPTS,
    COMPRESSION_RETRY_STEP_MB,
    COMPRESSION_TARGET_FILL_RATIO,
    CREATE_NO_WINDOW,
    MIN_COMPRESSION_BUDGET_MB,
    WINDOWS_MB_BYTES,
    format_windows_discord_size,
)
from cliptoolbox.core.commands import (
    build_compressed_export_command,
    build_standard_export_command,
    export_progress_duration,
    resolve_resolution_limit,
)


class ExportCallbacks(Protocol):
    """UI-facing events emitted by an export run.

    Implementations are responsible for marshaling onto the UI thread; the
    export job calls these from its worker thread.
    """

    def on_status(self, text: str) -> None: ...

    def on_log(self, text: str) -> None: ...

    def on_seek_to(self, seconds: float) -> None: ...

    def on_error(self, title: str, message: str) -> None: ...

    def on_complete(self, output_path: str, size_bytes: int | None) -> None: ...

    def on_finished(self) -> None: ...


def run_export_command(
    cmd: list[str],
    progress_duration: float,
    progress_label: str,
    total_duration_seconds: float | None,
    callbacks: ExportCallbacks,
    register_process: Callable[[subprocess.Popen | None], None],
) -> tuple[int, str]:
    export_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    register_process(export_process)

    last_percentage = -1

    if export_process.stdout:
        for line in export_process.stdout:
            line = line.strip()

            if line.startswith("out_time_ms=") and progress_duration > 0:
                try:
                    out_time_ms = int(line.split("=", 1)[1])
                    current_seconds = out_time_ms / 1_000_000
                    percentage = int((current_seconds / progress_duration) * 100)
                    percentage = max(0, min(100, percentage))

                    if percentage != last_percentage:
                        last_percentage = percentage
                        callbacks.on_status(f"{progress_label} {percentage}%")
                except Exception:
                    pass

            elif line == "progress=end":
                full_duration = total_duration_seconds or 0
                if full_duration:
                    callbacks.on_seek_to(full_duration)

    return_code = export_process.wait()

    stderr_text = ""
    if export_process.stderr:
        stderr_text = export_process.stderr.read()

    register_process(None)
    return return_code, stderr_text


def run_export_job(
    input_path: str,
    filter_complex: str,
    output_path: str,
    trim_start: float | None,
    trim_end: float | None,
    compression_target_mb: float | None,
    compression_resolution_label: str | None,
    total_duration_seconds: float | None,
    callbacks: ExportCallbacks,
    is_cancelled: Callable[[], bool],
    register_process: Callable[[subprocess.Popen | None], None],
):
    try:
        progress_duration = export_progress_duration(total_duration_seconds, trim_start, trim_end)
        full_duration = total_duration_seconds or 0

        if compression_target_mb is None:
            cmd = build_standard_export_command(
                input_path,
                filter_complex,
                output_path,
                trim_start,
                trim_end,
            )

            callbacks.on_log("Starting standard export: video copy + AAC mixed audio.")
            return_code, stderr_text = run_export_command(
                cmd,
                progress_duration,
                "Exporting...",
                total_duration_seconds,
                callbacks,
                register_process,
            )

            if return_code != 0:
                if not is_cancelled():
                    callbacks.on_error(
                        "Export Error",
                        "FFmpeg export failed.\n\n"
                        + (stderr_text[-3000:] if stderr_text else "No FFmpeg error output."),
                    )
                return

            if full_duration:
                callbacks.on_seek_to(trim_end or full_duration)

            callbacks.on_status(f"Export complete: {output_path}")
            callbacks.on_log(f"Export complete: {output_path}")
            callbacks.on_complete(output_path, None)
            return

        if progress_duration <= 0:
            raise ValueError("Cannot compress to a target size because the video duration is unknown.")

        _, _, compression_resolution_label = resolve_resolution_limit(compression_resolution_label)

        target_limit_bytes = int(compression_target_mb * WINDOWS_MB_BYTES)
        target_fill_bytes = int(target_limit_bytes * COMPRESSION_TARGET_FILL_RATIO)
        target_limit_mb = target_limit_bytes / WINDOWS_MB_BYTES

        budget_mb = float(compression_target_mb)
        lower_budget_mb: float | None = None
        upper_budget_mb: float | None = None

        last_error = ""
        stop_reason = ""
        final_size_bytes = 0
        best_size_bytes = 0
        best_temp_path: str | None = None
        temp_paths: list[str] = []

        callbacks.on_log(
            (
                f"Compression tuning target: keep the best file under {target_limit_mb:.2f} MB in Windows/Discord "
                f"and retry if it lands below {target_fill_bytes / WINDOWS_MB_BYTES:.2f} MB in Windows/Discord."
            ),
        )

        try:
            for attempt in range(1, COMPRESSION_MAX_ATTEMPTS + 1):
                if is_cancelled():
                    callbacks.on_log("Export cancelled.")
                    return

                if budget_mb < MIN_COMPRESSION_BUDGET_MB:
                    stop_reason = "The bitrate budget became too small to continue."
                    callbacks.on_log(f"Compression stopped: {stop_reason}")
                    break

                suffix = Path(output_path).suffix or ".mp4"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_output_path = temp_file.name
                temp_file.close()
                temp_paths.append(temp_output_path)

                try:
                    cmd, video_kbps, audio_kbps, total_kbps = build_compressed_export_command(
                        input_path,
                        filter_complex,
                        temp_output_path,
                        trim_start,
                        trim_end,
                        budget_mb,
                        progress_duration,
                        compression_resolution_label,
                    )
                except ValueError as exc:
                    stop_reason = str(exc)
                    callbacks.on_log(f"Compression stopped: {stop_reason}")
                    break

                callbacks.on_log(
                    (
                        f"Compression attempt {attempt}/{COMPRESSION_MAX_ATTEMPTS}: "
                        f"encode budget {budget_mb:.2f} MB internal, video {video_kbps} kbps, "
                        f"audio {audio_kbps} kbps. Video is capped to {compression_resolution_label} if needed; FPS is preserved."
                    ),
                )

                return_code, stderr_text = run_export_command(
                    cmd,
                    progress_duration,
                    f"Compressing attempt {attempt}...",
                    total_duration_seconds,
                    callbacks,
                    register_process,
                )

                if is_cancelled():
                    callbacks.on_log("Export cancelled.")
                    return

                if return_code != 0:
                    last_error = stderr_text[-3000:] if stderr_text else "No FFmpeg error output."
                    break

                try:
                    final_size_bytes = Path(temp_output_path).stat().st_size
                except Exception:
                    final_size_bytes = 0

                final_size_mb = final_size_bytes / WINDOWS_MB_BYTES if final_size_bytes else 0
                final_size_text = format_windows_discord_size(final_size_bytes)

                callbacks.on_log(
                    f"Compression attempt {attempt} finished at {final_size_text}. Limit is {target_limit_mb:.2f} MB in Windows/Discord.",
                )

                if final_size_bytes and final_size_bytes <= target_limit_bytes:
                    lower_budget_mb = budget_mb

                    if final_size_bytes > best_size_bytes:
                        if best_temp_path and best_temp_path != temp_output_path:
                            try:
                                Path(best_temp_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                        best_size_bytes = final_size_bytes
                        best_temp_path = temp_output_path
                    else:
                        try:
                            Path(temp_output_path).unlink(missing_ok=True)
                        except Exception:
                            pass

                    if final_size_bytes >= target_fill_bytes:
                        shutil.copy2(best_temp_path, output_path)

                        if full_duration:
                            callbacks.on_seek_to(trim_end or full_duration)

                        best_size_text = format_windows_discord_size(best_size_bytes)
                        callbacks.on_status(
                            f"Export complete: {output_path} ({best_size_text})",
                        )
                        callbacks.on_log(
                            (
                                f"Compression succeeded at {best_size_text} after {attempt} attempt(s), "
                                f"using the closest successful file under {target_limit_mb:.2f} MB in Windows/Discord."
                            ),
                        )
                        callbacks.on_complete(output_path, best_size_bytes)
                        return

                    if upper_budget_mb is not None:
                        next_budget_mb = (budget_mb + upper_budget_mb) / 2
                    else:
                        desired_bytes = max(target_fill_bytes, int(target_limit_bytes * 0.99))
                        ratio = desired_bytes / final_size_bytes if final_size_bytes else 1.0
                        next_budget_mb = budget_mb * ratio

                    next_budget_mb = max(budget_mb + COMPRESSION_BUDGET_EPSILON_MB, next_budget_mb)
                    callbacks.on_log(
                        (
                            f"File is under the limit but leaves room unused. "
                            f"Retrying with a {next_budget_mb:.2f} MB internal encode budget."
                        ),
                    )

                else:
                    upper_budget_mb = budget_mb

                    if lower_budget_mb is not None:
                        next_budget_mb = (lower_budget_mb + budget_mb) / 2
                    else:
                        if final_size_bytes:
                            ratio = target_fill_bytes / final_size_bytes
                            next_budget_mb = budget_mb * ratio
                        else:
                            next_budget_mb = budget_mb - COMPRESSION_RETRY_STEP_MB

                        next_budget_mb = min(next_budget_mb, budget_mb - COMPRESSION_BUDGET_EPSILON_MB)

                    callbacks.on_log(
                        (
                            f"File is too large. Retrying with a {next_budget_mb:.2f} MB internal encode budget "
                            f"while keeping the best previous under-limit file."
                        ),
                    )

                if abs(next_budget_mb - budget_mb) < COMPRESSION_BUDGET_EPSILON_MB:
                    stop_reason = "Further bitrate tuning would barely change the result."
                    callbacks.on_log(f"Compression stopped: {stop_reason}")
                    break

                budget_mb = next_budget_mb

            if best_temp_path and best_size_bytes:
                shutil.copy2(best_temp_path, output_path)

                if full_duration:
                    callbacks.on_seek_to(trim_end or full_duration)

                best_size_text = format_windows_discord_size(best_size_bytes)
                callbacks.on_status(
                    f"Export complete: {output_path} ({best_size_text})",
                )
                callbacks.on_log(
                    (
                        f"Compression finished using the best successful attempt: {best_size_text} "
                        f"under the {target_limit_mb:.2f} MB in Windows/Discord limit."
                    ),
                )
                callbacks.on_complete(output_path, best_size_bytes)
                return

        finally:
            for temp_path in temp_paths:
                if temp_path != best_temp_path:
                    try:
                        Path(temp_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            if best_temp_path:
                try:
                    Path(best_temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

        if last_error:
            callbacks.on_error(
                "Compression Error",
                "FFmpeg compression failed.\n\n"
                "This usually means hevc_nvenc is unavailable, the NVIDIA driver/GPU does not support it, "
                "or FFmpeg rejected the NVENC settings.\n\n"
                + last_error,
            )
        else:
            final_size_text = format_windows_discord_size(final_size_bytes)
            extra_reason = f"\n\nReason: {stop_reason}" if stop_reason else ""
            callbacks.on_error(
                "Compression Target Not Reached",
                f"The output could not be compressed below {compression_target_mb:g} MB in Windows/Discord.\n\n"
                f"Last size: {final_size_text}"
                f"{extra_reason}\n\n"
                "Try trimming the clip shorter or using a larger MB target.",
            )

    except Exception as exc:
        callbacks.on_error(
            "Export Error",
            f"Export failed:\n\n{exc}",
        )
        callbacks.on_log(f"Export failed: {exc}")

    finally:
        register_process(None)
        callbacks.on_finished()
