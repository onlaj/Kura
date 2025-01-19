import sys

from PyQt6.QtWidgets import QApplication

from core.media_handler import MediaHandler
from db.database import Database
from gui.main_window import MainWindow
from gui.ranking_tab import RankingTab
from gui.upload_tab import UploadTab
from gui.voting_tab import VotingTab


class Application:
    def __init__(self):
        """Initialize the application and its components."""
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

        # Initialize tabs
        self.init_tabs()

    def init_tabs(self):
        """Initialize all application tabs."""
        # Create tabs
        self.upload_tab = UploadTab(self.add_media_to_db)
        self.ranking_tab = RankingTab(
            self.get_rankings,
            self.media_handler,
            self.delete_media
        )
        self.voting_tab = VotingTab(
            self.get_pair_for_voting,
            self.update_ratings,
            self.media_handler
        )

        # Set up tabs in main window
        self.main_window.setup_tabs(
            self.voting_tab,
            self.upload_tab,
            self.ranking_tab
        )

    def add_media_to_db(self, file_path: str) -> bool:
        """Add media file to database if valid."""
        if self.media_handler.is_valid_media(file_path):
            return self.db.add_media(file_path)
        return False

    def delete_media(self, media_id: int):
        """Delete media from database"""
        try:
            file_path = self.db.delete_media(media_id)
            #if file_path and os.path.exists(file_path):
                #os.remove(file_path)
        except Exception as e:
            print(f"Error deleting media: {e}")
            raise e

    def get_rankings(self, page: int = 1, per_page: int = 50):
        """Get current rankings with pagination."""
        return self.db.get_rankings_page(page, per_page)

    def get_pair_for_voting(self):
        """Get a pair of media items for voting."""
        return self.db.get_pair_for_voting()

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