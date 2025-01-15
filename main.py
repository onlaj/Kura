# main.py

import os
from pathlib import Path
import customtkinter as ctk
from db.database import Database
from gui.main_window import MainWindow
from gui.upload_tab import UploadTab
from gui.ranking_tab import RankingTab
from gui.voting_tab import VotingTab
from core.image_handler import ImageHandler


class Application:
    def __init__(self):
        """Initialize the application and its components."""
        # Set appearance mode and default color theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Initialize database
        self.db = Database()

        # Initialize image handler
        self.image_handler = ImageHandler()

        # Create main window
        self.main_window = MainWindow()

        # Initialize tabs
        self.init_upload_tab()
        self.init_ranking_tab()
        self.init_voting_tab()

    def init_upload_tab(self):
        """Initialize the upload tab."""
        self.upload_tab = UploadTab(
            self.main_window.tab_upload,
            self.add_image_to_db
        )
        self.upload_tab.grid(row=0, column=0, sticky="nsew")

    def init_ranking_tab(self):
        """Initialize the ranking tab."""
        self.ranking_tab = RankingTab(
            self.main_window.tab_ranking,
            self.get_rankings,
            self.image_handler,
            self.delete_image  # Add delete callback
        )
        self.ranking_tab.grid(row=0, column=0, sticky="nsew")

    def init_voting_tab(self):
        """Initialize the voting tab."""
        self.voting_tab = VotingTab(
            self.main_window.tab_voting,
            self.get_pair_for_voting,
            self.update_ratings,
            self.image_handler
        )
        self.voting_tab.grid(row=0, column=0, sticky="nsew")

    def add_image_to_db(self, image_path: str) -> bool:
        """
        Add an image to the database if it's valid.

        Args:
            image_path: Path to the image file

        Returns:
            Boolean indicating if the image was successfully added
        """
        if self.image_handler.is_valid_image(image_path):
            return self.db.add_image(image_path)
        return False

    def delete_image(self, image_id: int):
        """
        Delete an image from the database and file system.

        Args:
            image_id: ID of the image to delete
        """
        try:
            # Delete from database and get file path
            image_path = self.db.delete_image(image_id)

            # Delete the actual file if it exists
            if image_path and os.path.exists(image_path):
                os.remove(image_path)

        except Exception as e:
            print(f"Error deleting image: {e}")
            raise e

    def get_rankings(self, page: int = 1, per_page: int = 50):
        """
        Get current rankings from database with pagination.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page

        Returns:
            Tuple of (list of image records, total number of images)
        """
        return self.db.get_rankings_page(page, per_page)

    def get_pair_for_voting(self):
        """
        Get a pair of images for voting.

        Returns:
            Tuple of two image records (id, path, rating, votes)
        """
        return self.db.get_pair_for_voting()

    def update_ratings(self, winner_id: int, loser_id: int,
                       new_winner_rating: float, new_loser_rating: float):
        """
        Update ratings after a vote.

        Args:
            winner_id: ID of the winning image
            loser_id: ID of the losing image
            new_winner_rating: New rating for the winner
            new_loser_rating: New rating for the loser
        """
        self.db.update_ratings(winner_id, loser_id,
                               new_winner_rating, new_loser_rating)

    def run(self):
        """Start the application."""
        self.main_window.start()

    def cleanup(self):
        """Clean up resources before exit."""
        self.db.close()


def main():
    app = Application()
    try:
        app.run()
    finally:
        app.cleanup()


if __name__ == "__main__":
    main()