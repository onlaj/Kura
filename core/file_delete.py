"""Cross-platform file deletion with retries and media-backend release helpers."""
import gc
import logging
import os
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

# Single-file / explicit Retry: a few short waits so Qt/WMF can drop the handle.
DEFAULT_ATTEMPTS = 3
INITIAL_DELAY_S = 0.1
# Mass delete: one try per file. Failures go to FailedDeleteDialog instead of blocking.
BATCH_ATTEMPTS = 1


def normalize_path(path: str) -> str:
    """Return a comparable absolute path (case-normalized on Windows)."""
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def paths_equal(path_a: str, path_b: str) -> bool:
    """True when two filesystem paths refer to the same location."""
    if not path_a or not path_b:
        return False
    return normalize_path(path_a) == normalize_path(path_b)


def pump_ui_events():
    """Let Qt Multimedia finish closing file handles (needed on Windows)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def release_qmediaplayer(player) -> None:
    """Stop a QMediaPlayer and clear its source so the OS can unlock the file."""
    if player is None:
        return
    from PyQt6.QtCore import QUrl
    try:
        player.stop()
        player.setSource(QUrl())
    except RuntimeError:
        pass
    except Exception as e:
        logger.debug(f"Could not release QMediaPlayer: {e}")


def release_qmovie(movie) -> None:
    """Stop a QMovie and clear its filename so the OS can unlock the file."""
    if movie is None:
        return
    try:
        movie.stop()
        movie.setFileName("")
    except RuntimeError:
        pass
    except Exception as e:
        logger.debug(f"Could not release QMovie: {e}")


def delete_file(file_path: str, *, pump_events: bool = False,
                attempts: int = DEFAULT_ATTEMPTS) -> Tuple[bool, Optional[str]]:
    """
    Delete a file from disk, preferring the trash, with retries and a final exists check.

    Args:
        file_path: Path to delete.
        pump_events: If True, process Qt events between retries (UI thread only).
        attempts: Maximum delete attempts. Use BATCH_ATTEMPTS (1) for mass
            delete so a lock on every file does not stall the whole operation.
            Failed files are reported to FailedDeleteDialog, whose Retry
            button uses the default (a few short waits).

    Returns:
        (True, None) if the file is gone (including if it was already missing).
        (False, error_message) if it is still on disk after all attempts.
    """
    if not file_path:
        return True, None
    if not os.path.exists(file_path):
        return True, None

    last_error = None
    delay = INITIAL_DELAY_S

    for i in range(attempts):
        try:
            if SEND2TRASH_AVAILABLE:
                try:
                    send2trash.send2trash(file_path)
                except Exception as trash_error:
                    logger.warning(
                        f"Failed to move to trash, attempting permanent deletion: {trash_error}"
                    )
                    os.remove(file_path)
            else:
                os.remove(file_path)
        except FileNotFoundError:
            return True, None
        except (PermissionError, OSError, Exception) as e:
            last_error = str(e)
            logger.warning(f"Error deleting file {file_path} (attempt {i + 1}/{attempts}): {e}")

        if not os.path.exists(file_path):
            logger.info(f"Deleted file: {file_path}")
            return True, None

        if last_error is None:
            last_error = "File still exists after delete"

        if i < attempts - 1:
            gc.collect()
            if pump_events:
                pump_ui_events()
            time.sleep(delay)
            delay *= 1.5

    return False, last_error or "File still exists after delete"
