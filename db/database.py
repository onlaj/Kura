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
        # Images table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                rating REAL DEFAULT 1200,
                votes INTEGER DEFAULT 0
            )
        """)

        # Votes history table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (winner_id) REFERENCES images (id),
                FOREIGN KEY (loser_id) REFERENCES images (id)
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

    def _recalculate_ratings(self):
        """Recalculate all ratings based on vote history."""
        print("RECALCULATING SCORES")
        from core.elo import Rating

        # Reset all ratings to default
        self.cursor.execute("""
            UPDATE images 
            SET rating = 1200, votes = 0
        """)

        # Get all votes ordered by timestamp
        self.cursor.execute("""
            SELECT winner_id, loser_id 
            FROM votes 
            ORDER BY timestamp ASC
        """)
        votes = self.cursor.fetchall()

        print(f"Processing {len(votes)} votes...")

        # Create a dictionary to track current ratings
        self.cursor.execute("SELECT id, rating FROM images")
        ratings = {row[0]: 1200 for row in self.cursor.fetchall()}

        # Process each vote
        for winner_id, loser_id in votes:
            if winner_id in ratings and loser_id in ratings:
                # Calculate new ratings
                rating = Rating(
                    ratings[winner_id],  # Use current rating from our tracking dict
                    ratings[loser_id],  # Use current rating from our tracking dict
                    Rating.WIN,
                    Rating.LOST
                )
                new_ratings = rating.get_new_ratings()

                # Update our tracking dictionary
                ratings[winner_id] = new_ratings['a']
                ratings[loser_id] = new_ratings['b']

                # Update vote counts in database
                self.cursor.execute("""
                    UPDATE images 
                    SET votes = votes + 1 
                    WHERE id IN (?, ?)
                """, (winner_id, loser_id))

        print("Updating final ratings in database...")

        # Update all final ratings in the database
        for image_id, final_rating in ratings.items():
            self.cursor.execute("""
                UPDATE images 
                SET rating = ? 
                WHERE id = ?
            """, (final_rating, image_id))

        self.conn.commit()
        print("Recalculation complete!")

    def delete_image(self, image_id: int):
        """
        Delete an image and recalculate all ratings.

        Args:
            image_id: ID of the image to delete
        """
        try:
            # Start transaction
            self.conn.execute("BEGIN")

            # Get image path for file deletion
            self.cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
            image_path = self.cursor.fetchone()

            # Delete related votes
            self.cursor.execute("""
                DELETE FROM votes 
                WHERE winner_id = ? OR loser_id = ?
            """, (image_id, image_id))

            # Delete the image record
            self.cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))

            # Recalculate all ratings
            self._recalculate_ratings()

            # Commit transaction
            self.conn.commit()

            # Return path for file deletion
            return image_path[0] if image_path else None

        except Exception as e:
            self.conn.rollback()
            raise e

    def update_ratings(self, winner_id: int, loser_id: int,
                       new_winner_rating: float, new_loser_rating: float):
        """Update ratings after a vote."""
        try:
            self.conn.execute("BEGIN")

            # Update ratings
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

            # Record the vote
            self.cursor.execute("""
                INSERT INTO votes (winner_id, loser_id)
                VALUES (?, ?)
            """, (winner_id, loser_id))

            self.conn.commit()

        except Exception as e:
            self.conn.rollback()
            raise e

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