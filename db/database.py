# db/database.py

import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_path: str = "media_ratings.db"):
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
        # Media table (renamed from images)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                rating REAL DEFAULT 1200,
                votes INTEGER DEFAULT 0,
                type TEXT NOT NULL  -- New column for media type
            )
        """)

        # Create an index on the type column for faster filtering
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_media_type ON media (type)
        """)

        # Votes history table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (winner_id) REFERENCES media (id),
                FOREIGN KEY (loser_id) REFERENCES media (id)
            )
        """)

        self.conn.commit()

    def add_media(self, file_path: str, media_type: str) -> bool:
        """
        Add a new media file to the database.

        Args:
            file_path: Path to the media file
            media_type: Type of media (image, gif, video)

        Returns:
            bool: True if media was added successfully, False if it already exists
        """
        try:
            # Normalize the path to handle different path formats
            normalized_path = str(Path(file_path).resolve())

            # Check if the file already exists in the database
            self.cursor.execute(
                "SELECT id FROM media WHERE path = ?",
                (normalized_path,)
            )
            if self.cursor.fetchone():
                return False

            self.cursor.execute(
                "INSERT INTO media (path, type) VALUES (?, ?)",
                (normalized_path, media_type)
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
            UPDATE media 
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
        self.cursor.execute("SELECT id, rating FROM media")
        ratings = {row[0]: 1200 for row in self.cursor.fetchall()}

        # Process each vote
        for winner_id, loser_id in votes:
            if winner_id in ratings and loser_id in ratings:
                # Calculate new ratings
                rating = Rating(
                    ratings[winner_id],
                    ratings[loser_id],
                    Rating.WIN,
                    Rating.LOST
                )
                new_ratings = rating.get_new_ratings()

                # Update our tracking dictionary
                ratings[winner_id] = new_ratings['a']
                ratings[loser_id] = new_ratings['b']

                # Update vote counts in database
                self.cursor.execute("""
                    UPDATE media 
                    SET votes = votes + 1 
                    WHERE id IN (?, ?)
                """, (winner_id, loser_id))

        print("Updating final ratings in database...")

        # Update all final ratings in the database
        for media_id, final_rating in ratings.items():
            self.cursor.execute("""
                UPDATE media 
                SET rating = ? 
                WHERE id = ?
            """, (final_rating, media_id))

        self.conn.commit()
        print("Recalculation complete!")

    def delete_media(self, media_id: int, recalculate: bool = True) -> Optional[str]:
        """
        Delete a media file and optionally recalculate all ratings.

        Args:
            media_id: ID of the media to delete
            recalculate: Whether to recalculate ratings after deletion (default: True)

        Returns:
            Optional[str]: Path of the deleted media file, or None if not found
        """
        try:
            # Start transaction
            self.conn.execute("BEGIN")

            # Get media path for file deletion
            self.cursor.execute("SELECT path FROM media WHERE id = ?", (media_id,))
            media_path = self.cursor.fetchone()

            # Delete related votes
            self.cursor.execute("""
                DELETE FROM votes 
                WHERE winner_id = ? OR loser_id = ?
            """, (media_id, media_id))

            # Delete the media record
            self.cursor.execute("DELETE FROM media WHERE id = ?", (media_id,))

            # Recalculate all ratings (if requested)
            if recalculate:
                self._recalculate_ratings()

            # Commit transaction
            self.conn.commit()

            # Return path for file deletion
            return media_path[0] if media_path else None

        except Exception as e:
            self.conn.rollback()
            raise e

    def update_ratings(self, winner_id: int, loser_id: int,
                       new_winner_rating: float, new_loser_rating: float):
        """
        Update ratings after a vote.

        Args:
            winner_id: ID of the winning media
            loser_id: ID of the losing media
            new_winner_rating: New rating for the winner
            new_loser_rating: New rating for the loser
        """
        try:
            self.conn.execute("BEGIN")

            # Update ratings
            self.cursor.execute("""
                UPDATE media 
                SET rating = ?, votes = votes + 1 
                WHERE id = ?
            """, (new_winner_rating, winner_id))

            self.cursor.execute("""
                UPDATE media 
                SET rating = ?, votes = votes + 1 
                WHERE id = ?
            """, (new_loser_rating, loser_id))

            # Record the vote
            self.cursor.execute("""
                INSERT INTO votes (winner_id, loser_id)
                VALUES (?, ?)
            """, (winner_id, loser_id))

            # Get the ID of the inserted vote
            vote_id = self.cursor.lastrowid

            # Verify the vote was recorded
            self.cursor.execute("""
                SELECT * FROM votes WHERE id = ?
            """, (vote_id,))
            vote_record = self.cursor.fetchone()
            print(
                f"Recorded vote: ID={vote_record[0]}, Winner={vote_record[1]}, Loser={vote_record[2]}, Time={vote_record[3]}")

            # Get total vote count
            self.cursor.execute("SELECT COUNT(*) FROM votes")
            total_votes = self.cursor.fetchone()[0]
            print(f"Total votes in database: {total_votes}")

            self.conn.commit()

        except Exception as e:
            self.conn.rollback()
            print(f"Error recording vote: {e}")
            raise e

    def get_rankings_page(self, page: int, per_page: int = 50, media_type: str = "all") -> Tuple[List[tuple], int]:
        """
        Get a page of ranked media items.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page
            media_type: Type of media to filter by (all, image, gif, video)

        Returns:
            Tuple of (list of media records, total number of items)
        """
        # Get total count
        if media_type == "all":
            self.cursor.execute("SELECT COUNT(*) FROM media")
        else:
            self.cursor.execute("SELECT COUNT(*) FROM media WHERE type = ?", (media_type,))
        total_items = self.cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * per_page

        # Get page of media items
        if media_type == "all":
            self.cursor.execute("""
                SELECT id, path, rating, votes 
                FROM media 
                ORDER BY rating DESC
                LIMIT ? OFFSET ?
            """, (per_page, offset))
        else:
            self.cursor.execute("""
                SELECT id, path, rating, votes 
                FROM media 
                WHERE type = ?
                ORDER BY rating DESC
                LIMIT ? OFFSET ?
            """, (media_type, per_page, offset))

        return self.cursor.fetchall(), total_items

    def get_pair_for_voting(self) -> Tuple[Optional[tuple], Optional[tuple]]:
        """
        Get two media items for voting: one least voted and one random.

        Returns:
            Tuple of (least voted media, random media), where each is a tuple of
            (id, path, rating, votes) or None if not enough media items exist
        """
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM media 
            ORDER BY votes ASC, RANDOM() 
            LIMIT 1
        """)
        least_voted = self.cursor.fetchone()

        if not least_voted:
            return None, None

        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE id != ? 
            ORDER BY RANDOM() 
            LIMIT 1
        """, (least_voted[0],))
        random_media = self.cursor.fetchone()

        return least_voted, random_media

    def close(self):
        """Close the database connection."""
        self.conn.close()