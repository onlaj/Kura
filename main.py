import sys

from PyQt6.QtWidgets import QApplication

from core.media_handler import MediaHandler
from db.database import Database
from gui.main_window import MainWindow
from gui.ranking_tab import RankingTab
from gui.upload_tab import UploadTab
from gui.voting_tab import VotingTab
from utils.config import setup_logging
from gui.albums_tab import AlbumsTab


class Application:
    def __init__(self):
        """Initialize the application and its components."""
        # Set up logging
        setup_logging()

        # Create Qt application
        self.app = QApplication(sys.argv)

        # Set application style
        self.app.setStyle('Fusion')

        # Initialize database
        self.db = Database()

        # Initialize media handler
        self.media_handler = MediaHandler()

        # Create main window
        self.main_window = MainWindow()

        self.active_album_id = 1  # Default album

        # Initialize tabs
        self.init_tabs()

    def init_tabs(self):
        """Initialize all application tabs."""
        # Create tabs
        self.albums_tab = AlbumsTab(self.db)
        self.albums_tab.album_changed.connect(self.on_album_changed)

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
            self.ranking_tab
        )

        self.upload_tab = UploadTab(self.add_media_to_db, self.media_handler, self.ranking_tab)

        # Set up tabs in main window
        self.main_window.setup_tabs(
            self.albums_tab,
            self.voting_tab,
            self.upload_tab,
            self.ranking_tab
        )

    def on_album_changed(self, album_id: int, album_name: str):
        """Handle album changes."""
        self.active_album_id = album_id
        self.voting_tab.set_active_album(album_id)  # Update VotingTab
        self.ranking_tab.set_active_album(album_id)  # Update RankingTab
        self.main_window.on_album_changed(album_id, album_name)  # Update window title

    def add_media_to_db(self, file_path: str, media_type: str) -> bool:
        """Add media file to database if valid."""
        if self.media_handler.is_valid_media(file_path):
            result = self.db.add_media(file_path, media_type, self.active_album_id)
            if result:
                self.ranking_tab.invalidate_total_media_count_cache()  # Invalidate cache
            return result
        return False

    def delete_media(self, media_id: int, recalculate: bool = True):
        """Delete media from database and return the file path."""
        try:
            file_path = self.db.delete_media(media_id, recalculate=recalculate)
            self.ranking_tab.invalidate_total_media_count_cache()  # Invalidate cache
            return file_path
        except Exception as e:
            print(f"Error deleting media: {e}")
            raise e

    def get_rankings(self, page: int = 1, per_page: int = 50, media_type: str = "all", album_id: int = 1):
        """Get current rankings with pagination and album filtering."""
        return self.db.get_rankings_page(page, per_page, media_type, album_id)

    def get_pair_for_voting(self, album_id: int = 1):
        """Get a pair of media items for voting from specified album."""
        return self.db.get_pair_for_voting(album_id)

    def update_ratings(self, winner_id: int, loser_id: int,
                       new_winner_rating: float, new_loser_rating: float):
        """Update ratings after a vote."""
        self.db.update_ratings(
            winner_id, loser_id,
            new_winner_rating, new_loser_rating
        )

    def run(self):
        """Start the application."""
        self.main_window.show()
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