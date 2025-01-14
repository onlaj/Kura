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
        """
        Add a new image to the database.

        Args:
            image_path: Path to the image file

        Returns:
            True if successful, False if image already exists
        """
        try:
            self.cursor.execute(
                "INSERT INTO images (path) VALUES (?)",
                (str(Path(image_path)),)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_pair_for_voting(self) -> Tuple[Optional[tuple], Optional[tuple]]:
        """
        Get two images for voting: one least voted and one random.

        Returns:
            Tuple of two image records (id, path, rating, votes)
        """
        # Get least voted image
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM images 
            ORDER BY votes ASC, RANDOM() 
            LIMIT 1
        """)
        least_voted = self.cursor.fetchone()

        if not least_voted:
            return None, None

        # Get random image different from the least voted one
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
        """
        Update ratings after a vote.

        Args:
            winner_id: ID of the winning image
            loser_id: ID of the losing image
            new_winner_rating: New ELO rating for winner
            new_loser_rating: New ELO rating for loser
        """
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

    def get_rankings(self) -> List[tuple]:
        """
        Get all images sorted by rating.

        Returns:
            List of (id, path, rating, votes) tuples
        """
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM images 
            ORDER BY rating DESC
        """)
        return self.cursor.fetchall()

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()