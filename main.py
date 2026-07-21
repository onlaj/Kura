import logging
import sys
import platform

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from core.media_handler import MediaHandler
from core.media_workers import MissingFilesScanWorker
from db.database import Database
from gui.history_tab import HistoryTab
from gui.main_window import MainWindow
from gui.missing_files_dialog import MissingFilesDialog
from gui.ranking_tab import RankingTab
from gui.load_tab import LoadTab
from gui.voting_tab import VotingTab
from utils.config import setup_logging
from gui.albums_tab import AlbumsTab
import os

__version__ = "1.2.0"

logger = logging.getLogger(__name__)

# Platform-specific icon handling
if platform.system() == 'Windows':
    import ctypes
    myappid = u'mycompany.myproduct.subproduct.version' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
elif platform.system() == 'Linux':
    # Ensure icon is visible in Linux desktop environments
    import os
    if not os.environ.get('DESKTOP_SESSION'):
        os.environ['DESKTOP_SESSION'] = 'generic'

def excepthook(exc_type, exc_value, exc_tb):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.exit(1)

sys.excepthook = excepthook

def qt_message_handler(mode, context, message):
    if mode == QtMsgType.QtFatalMsg:
        logging.critical(f"Fatal Qt error: {message}")
        sys.exit(1)
    else:
        logging.debug(f"Qt message: {message}")

qInstallMessageHandler(qt_message_handler)

class Application:
    def __init__(self):
        sys.excepthook = excepthook
        """Initialize the application and its components."""
        # Set up logging
        setup_logging()

        # Create Qt application
        self.app = QApplication(sys.argv)

        # Set application style
        self.app.setStyle('Fusion')

        # Set application icon - more robust path handling
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'logo.png')
        self.app.setWindowIcon(QIcon(icon_path))

        # Initialize database
        self.db = Database()

        # Initialize media handler
        self.media_handler = MediaHandler()

        # Create main window
        self.main_window = MainWindow(self.media_handler)

        self.history_tab = HistoryTab(self.db, self.media_handler)

        self.active_album_id = 1  # Default album

        # Missing files scan state
        self._scan_workers = []
        self._scan_progress = None
        self._scan_progress_worker = None  # Worker the progress dialog belongs to
        self._scanned_album_ids = set()  # Albums already auto-scanned this session

        # Initialize tabs
        self.init_tabs()

    def init_tabs(self):
        """Initialize all application tabs."""
        # Create tabs
        self.albums_tab = AlbumsTab(self.db)
        self.albums_tab.album_changed.connect(self.on_album_changed)
        self.albums_tab.check_missing_requested.connect(
            lambda: self.check_missing_files(album_id=None, manual=True)
        )

        self.ranking_tab = RankingTab(
            self.get_rankings,
            self.media_handler,
            self.delete_media,
            self.db
        )
        self.voting_tab = VotingTab(
            self.get_pair_for_voting,
            self.update_ratings,
            self.media_handler,
            self.ranking_tab,
            self.get_total_media_count,
            self.get_total_votes,
            get_album_rating_system=self.db.get_album_rating_system,
            get_mean_glicko_phi=self.db.get_mean_glicko_phi,
        )

        # Set history tab reference in voting tab
        self.voting_tab.set_history_tab(self.history_tab)

        self.upload_tab = LoadTab(
            self.add_media_to_db,
            self.media_handler,
            self.ranking_tab,
            lambda: self.active_album_id
        )

        # Set up tabs in main window
        self.main_window.setup_tabs(
            self.albums_tab,
            self.voting_tab,
            self.upload_tab,
            self.ranking_tab,
            self.history_tab
        )

    def get_total_media_count(self, album_id: int) -> int:
        return self.db.get_total_media_count(album_id)

    def get_total_votes(self, album_id: int) -> int:
        return self.db.get_total_votes(album_id)

    def on_album_changed(self, album_id: int, album_name: str):
        """Handle album changes."""
        self.active_album_id = album_id
        self.voting_tab.set_active_album(album_id)  # Update VotingTab
        self.ranking_tab.set_active_album(album_id)  # Update RankingTab
        self.main_window.on_album_changed(album_id, album_name)  # Update window title
        self.history_tab.set_active_album(album_id)
        self.check_missing_files(album_id=album_id)

    def check_missing_files(self, album_id: int = None, manual: bool = False):
        """
        Start a background check for media records whose files are missing on disk.

        Args:
            album_id: Album to check, or None to check all albums
            manual: True when triggered by the user (always rescans and reports
                    even when nothing is missing); automatic scans run once per
                    album per session and stay silent unless files are missing
        """
        if not manual:
            if album_id in self._scanned_album_ids:
                return
            self._scanned_album_ids.add(album_id)

        rows = self.db.get_media_paths_for_scan(album_id)
        if not rows:
            if manual:
                QMessageBox.information(
                    self.main_window, "Missing Files Check", "There are no media files to check."
                )
            return

        # Drop any scan that is still running; its result would be stale.
        # Cancelled workers still emit finished, where they get removed
        # from _scan_workers and their results are discarded.
        for worker in self._scan_workers:
            worker.cancel()
        if self._scan_progress:
            self._scan_progress.close()
            self._scan_progress = None
            self._scan_progress_worker = None

        worker = MissingFilesScanWorker(rows)
        self._scan_workers.append(worker)

        if manual:
            self._scan_progress = QProgressDialog(
                "Checking files on disk...", "Cancel", 0, len(rows), self.main_window
            )
            self._scan_progress_worker = worker
            self._scan_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._scan_progress.canceled.connect(worker.cancel)
            worker.progress.connect(self._on_missing_scan_progress)
            self._scan_progress.show()

        worker.finished.connect(
            lambda missing, w=worker, m=manual: self._on_missing_scan_finished(missing, w, m)
        )
        worker.start()

    def _on_missing_scan_progress(self, current: int, total: int):
        if self._scan_progress:
            self._scan_progress.setValue(current)

    def _on_missing_scan_finished(self, missing: list, worker, manual: bool):
        """Show the review dialog when the background scan found missing files."""
        if worker in self._scan_workers:
            self._scan_workers.remove(worker)
        worker.wait()  # run() has returned; ensure the thread is fully down

        if self._scan_progress is not None and self._scan_progress_worker is worker:
            self._scan_progress.close()
            self._scan_progress = None
            self._scan_progress_worker = None

        # A cancelled scan has a partial, stale result; discard it silently
        if worker.was_cancelled():
            return

        if not missing:
            if manual:
                QMessageBox.information(
                    self.main_window, "Missing Files Check", "All files are present on disk."
                )
            return

        dialog = MissingFilesDialog(self.db, missing, parent=self.main_window)
        dialog.files_changed.connect(self.on_missing_files_changed)
        dialog.exec()

    def on_missing_files_changed(self):
        """Refresh the UI after missing-file records were removed or relocated."""
        self.ranking_tab.invalidate_total_media_count_cache()
        self.voting_tab.refresh_media_count()
        self.albums_tab.refresh_albums()
        self.ranking_tab.refresh_rankings()

    def add_media_to_db(self, file_path: str, media_type: str) -> bool:
        """Add media file to database if valid."""
        if self.media_handler.is_valid_media(file_path):
            result = self.db.add_media(file_path, media_type, self.active_album_id)
            if result:
                self.ranking_tab.invalidate_total_media_count_cache()
                self.voting_tab.refresh_media_count()
                self.albums_tab.refresh_albums()  # Add this line
            return result
        return False

    def delete_media(self, media_id: int, recalculate: bool = True):
        """Delete media from database and return the file path."""
        try:
            file_path = self.db.delete_media(media_id, recalculate=recalculate)
            self.ranking_tab.invalidate_total_media_count_cache()
            self.voting_tab.refresh_media_count()
            self.albums_tab.refresh_albums()  # Add this line
            return file_path
        except Exception as e:
            raise e

    def get_rankings(self, page: int = 1, per_page: int = 50,
                    media_type: str = "all", album_id: int = 1,
                    sort_by: str = "rating", sort_order: str = "DESC", search_query: str = None):
        """Get current rankings with pagination, filtering, and sorting."""
        return self.db.get_rankings_page(
            page, per_page, media_type, album_id, sort_by, sort_order, search_query
        )


    def get_pair_for_voting(self, album_id: int = 1):
        """Get a pair of media items for voting from specified album."""
        return self.db.get_pair_for_voting(album_id)

    def update_ratings(self, winner_id: int, loser_id: int, album_id: int, weight: int = 1):
        """Update ratings after a vote (weight amplifies a single edge)."""
        self.db.update_ratings(winner_id, loser_id, album_id, weight=weight)

    def run(self):
        """Start the application."""
        self.main_window.show()
        # Check the initial album once the window is up
        QTimer.singleShot(500, lambda: self.check_missing_files(album_id=self.active_album_id))
        return self.app.exec()

    def cleanup(self):
        """Clean up resources before exit."""
        self.db.close()


def main():
    app = Application()
    try:
        return app.run()
    finally:
        app.cleanup()


if __name__ == "__main__":
    sys.exit(main())