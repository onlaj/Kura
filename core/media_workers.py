import os
import sqlite3
import logging
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from db.database import Database, get_database_path
from core.album_io import export_album, import_album

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

logger = logging.getLogger(__name__)


class MediaAddWorker(QThread):
    """Worker thread for adding multiple media files to the database."""
    file_processed = pyqtSignal(str, bool, str)  # file_path, success, message
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int, int)  # added_count, skipped_count

    def __init__(self, file_paths, media_handler, album_id, db_path=None):
        super().__init__()
        self.file_paths = file_paths
        self.media_handler = media_handler
        self.album_id = album_id
        self.db_path = db_path or get_database_path()
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

    def run(self):
        """Process files in background thread."""
        added_count = 0
        skipped_count = 0
        total = len(self.file_paths)

        # Create a new database connection for this thread
        db = Database(self.db_path)

        try:
            for index, file_path in enumerate(self.file_paths):
                if self._cancelled:
                    break

                try:
                    file_path_str = str(file_path)
                    if not self.media_handler.is_valid_media(file_path_str):
                        self.file_processed.emit(
                            file_path_str, False, "Invalid media type"
                        )
                        skipped_count += 1
                        continue

                    media_type = self.media_handler.get_media_type(file_path_str)
                    if db.add_media(file_path_str, media_type, self.album_id):
                        self.file_processed.emit(
                            file_path_str, True, f"Added ({media_type})"
                        )
                        added_count += 1
                    else:
                        self.file_processed.emit(
                            file_path_str, False, "Already exists"
                        )
                        skipped_count += 1
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    self.file_processed.emit(
                        file_path_str, False, f"Error: {str(e)}"
                    )
                    skipped_count += 1

                # Emit progress
                self.progress.emit(index + 1, total)

        finally:
            db.close()
            self.finished.emit(added_count, skipped_count)


class FileSearchWorker(QThread):
    """Worker thread for searching files in the filesystem."""
    file_found = pyqtSignal(int, list)  # media_id, matches
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal()

    def __init__(self, missing_files, search_dir):
        super().__init__()
        self.missing_files = missing_files  # List of dicts with id, filename, file_size
        self.search_dir = search_dir
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

    def run(self):
        """Search for files in background thread."""
        total = len(self.missing_files)

        for index, media in enumerate(self.missing_files):
            if self._cancelled:
                break

            matches = []
            target_name = media['filename']
            target_size = media['file_size']

            # Recursive search
            try:
                for root, _, files in os.walk(self.search_dir):
                    if self._cancelled:
                        break

                    for file in files:
                        if file == target_name:
                            full_path = os.path.join(root, file)
                            try:
                                if os.path.getsize(full_path) == target_size:
                                    matches.append(full_path)
                            except OSError:
                                continue

                # Emit result
                self.file_found.emit(media['id'], matches)
            except Exception as e:
                logger.error(f"Error searching for {target_name}: {e}")
                self.file_found.emit(media['id'], [])

            # Emit progress
            self.progress.emit(index + 1, total)

        self.finished.emit()


class AlbumExportWorker(QThread):
    """Worker thread for exporting albums."""
    progress = pyqtSignal(str)  # status message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, db_path, album_id, file_path):
        super().__init__()
        self.db_path = db_path
        self.album_id = album_id
        self.file_path = file_path

    def run(self):
        """Export album in background thread."""
        # Create a new database connection for this thread
        db = Database(self.db_path)
        try:
            self.progress.emit("Exporting album data...")
            export_album(db, self.album_id, self.file_path)
            self.finished.emit(True, "Album exported successfully.")
        except Exception as e:
            logger.error(f"Error exporting album: {e}")
            self.finished.emit(False, f"Export failed: {str(e)}")
        finally:
            db.close()


class AlbumImportWorker(QThread):
    """Worker thread for importing albums."""
    progress = pyqtSignal(str)  # status message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, db_path, file_path, new_name):
        super().__init__()
        self.db_path = db_path
        self.file_path = file_path
        self.new_name = new_name

    def run(self):
        """Import album in background thread."""
        # Create a new database connection for this thread
        db = Database(self.db_path)
        try:
            self.progress.emit("Reading backup file...")
            success, message = import_album(db, self.file_path, self.new_name)
            self.finished.emit(success, message)
        except Exception as e:
            logger.error(f"Error importing album: {e}")
            self.finished.emit(False, f"Import failed: {str(e)}")
        finally:
            db.close()


class MediaDeleteWorker(QThread):
    """Worker thread for deleting multiple media files."""
    file_deleted = pyqtSignal(int, bool, str)  # media_id, success, error_message
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int, int)  # success_count, error_count

    def __init__(self, media_items, delete_from_disk, db_path=None):
        """
        Initialize the worker.
        
        Args:
            media_items: List of tuples (media_id, file_path)
            delete_from_disk: Whether to delete files from disk
            db_path: Path to database (optional)
        """
        super().__init__()
        self.media_items = media_items
        self.delete_from_disk = delete_from_disk
        self.db_path = db_path or get_database_path()
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

    def run(self):
        """Delete media items in background thread."""
        success_count = 0
        error_count = 0
        total = len(self.media_items)

        # Create a new database connection for this thread
        db = Database(self.db_path)

        try:
            for index, (media_id, file_path) in enumerate(self.media_items):
                if self._cancelled:
                    break

                error_message = None
                success = False

                try:
                    # Delete from database (without recalculating ratings yet)
                    deleted_path = db.delete_media(media_id, recalculate=False)
                    
                    # Delete file from disk if requested
                    if self.delete_from_disk and deleted_path:
                        if os.path.exists(deleted_path):
                            try:
                                # Try to move to trash first
                                if SEND2TRASH_AVAILABLE:
                                    try:
                                        send2trash.send2trash(deleted_path)
                                    except Exception:
                                        # Fall back to permanent deletion if trash fails
                                        os.remove(deleted_path)
                                else:
                                    # Fall back to permanent deletion if send2trash not available
                                    os.remove(deleted_path)
                            except Exception as e:
                                error_message = f"Failed to delete file: {str(e)}"
                                logger.error(f"Error deleting file {deleted_path}: {e}")

                    success = True
                    success_count += 1
                except Exception as e:
                    error_message = str(e)
                    error_count += 1
                    logger.error(f"Error deleting media {media_id}: {e}")

                # Emit result
                self.file_deleted.emit(media_id, success, error_message or "")

                # Emit progress
                self.progress.emit(index + 1, total)

            # Recalculate ratings once after all deletions
            if not self._cancelled:
                try:
                    db._recalculate_ratings()
                except Exception as e:
                    logger.error(f"Error recalculating ratings: {e}")

        finally:
            db.close()
            self.finished.emit(success_count, error_count)

