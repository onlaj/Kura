# db/database.py

import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_path: str = "image_ratings.db"):
        """
        Initialize database connection and create tables if they don't exist.

        Args:
            db_path: Path to the SQLite database file
        """
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        """Create necessary database tables if they don't exist."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                rating REAL DEFAULT 1200,
                votes INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def add_image(self, image_path: str) -> bool:
        """Add a new image to the database."""
        try:
            self.cursor.execute(
                "INSERT INTO images (path) VALUES (?)",
                (str(Path(image_path)),)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_rankings_page(self, page: int, per_page: int = 50) -> Tuple[List[tuple], int]:
        """
        Get a page of ranked images.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page

        Returns:
            Tuple of (list of image records, total number of images)
        """
        # Get total count
        self.cursor.execute("SELECT COUNT(*) FROM images")
        total_images = self.cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * per_page

        # Get page of images
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM images 
            ORDER BY rating DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))

        return self.cursor.fetchall(), total_images

    def get_pair_for_voting(self) -> Tuple[Optional[tuple], Optional[tuple]]:
        """Get two images for voting: one least voted and one random."""
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM images 
            ORDER BY votes ASC, RANDOM() 
            LIMIT 1
        """)
        least_voted = self.cursor.fetchone()

        if not least_voted:
            return None, None

        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM images 
            WHERE id != ? 
            ORDER BY RANDOM() 
            LIMIT 1
        """, (least_voted[0],))
        random_image = self.cursor.fetchone()

        return least_voted, random_image

    def update_ratings(self, winner_id: int, loser_id: int,
                       new_winner_rating: float, new_loser_rating: float):
        """Update ratings after a vote."""
        self.cursor.execute("""
            UPDATE images 
            SET rating = ?, votes = votes + 1 
            WHERE id = ?
        """, (new_winner_rating, winner_id))

        self.cursor.execute("""
            UPDATE images 
            SET rating = ?, votes = votes + 1 
            WHERE id = ?
        """, (new_loser_rating, loser_id))

        self.conn.commit()

    def close(self):
        """Close the database connection."""
        self.conn.close()