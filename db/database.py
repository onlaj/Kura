# db/database.py
import os
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
        self._create_indices()
        self._ensure_default_album()

    def _create_indices(self):
        """Create indices for efficient sorting and filtering."""
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_media_rating ON media (rating)",
            "CREATE INDEX IF NOT EXISTS idx_media_votes ON media (votes)",
            "CREATE INDEX IF NOT EXISTS idx_media_path ON media (path)",  # For filename sorting
            "CREATE INDEX IF NOT EXISTS idx_media_file_size ON media (file_size)",
            "CREATE INDEX IF NOT EXISTS idx_media_type ON media (type)",  # Already existed
            "CREATE INDEX IF NOT EXISTS idx_media_album ON media (album_id)"  # For album filtering
        ]

        for index in indices:
            self.cursor.execute(index)
        self.conn.commit()

    def _create_tables(self):
        """Create necessary database tables if they don't exist."""
        # Albums table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Media table with album support
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                rating REAL DEFAULT 1200,
                votes INTEGER DEFAULT 0,
                type TEXT NOT NULL,
                album_id INTEGER NOT NULL,
                file_size INTEGER,
                FOREIGN KEY (album_id) REFERENCES albums (id),
                UNIQUE(path, album_id)
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

    def _ensure_default_album(self):
        """Ensure default album exists"""
        self.cursor.execute("""
            INSERT OR IGNORE INTO albums (id, name) VALUES (1, 'Default')
        """)
        self.conn.commit()

    def create_album(self, name: str) -> bool:
        """Create a new album."""
        try:
            self.cursor.execute("INSERT INTO albums (name) VALUES (?)", (name,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_album(self, album_id: int, new_name: str) -> bool:
        """Rename an album."""
        if album_id == 1:  # Default album can't be renamed
            return False
        try:
            self.cursor.execute("UPDATE albums SET name = ? WHERE id = ?", (new_name, album_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_album(self, album_id: int) -> bool:
        """Delete an album and all its media."""
        if album_id == 1:  # Default album can't be deleted
            return False
        try:
            self.conn.execute("BEGIN")
            # Delete all votes involving media from this album
            self.cursor.execute("""
                DELETE FROM votes WHERE winner_id IN 
                (SELECT id FROM media WHERE album_id = ?)
                OR loser_id IN (SELECT id FROM media WHERE album_id = ?)
            """, (album_id, album_id))
            # Delete all media in the album
            self.cursor.execute("DELETE FROM media WHERE album_id = ?", (album_id,))
            # Delete the album
            self.cursor.execute("DELETE FROM albums WHERE id = ?", (album_id,))
            self.conn.commit()
            return True
        except:
            self.conn.rollback()
            return False

    def get_albums(self) -> List[tuple]:
        """Get all albums."""
        self.cursor.execute("SELECT id, name FROM albums ORDER BY id")
        return self.cursor.fetchall()

    def add_media(self, file_path: str, media_type: str, album_id: int) -> bool:
        """
        Add a new media file to the database.

        Args:
            file_path: Path to the media file
            media_type: Type of media (image, gif, video)
            album_id: ID of the album to add the media to

        Returns:
            bool: True if media was added successfully, False if it already exists
        """
        try:
            # Normalize the path to handle different path formats
            normalized_path = str(Path(file_path).resolve())

            # Get the file size
            file_size = os.path.getsize(normalized_path)

            # Check if the file already exists in the database
            self.cursor.execute(
                "SELECT id FROM media WHERE path = ? AND album_id = ?",
                (normalized_path, album_id)
            )
            if self.cursor.fetchone():
                return False

            self.cursor.execute(
                "INSERT INTO media (path, type, album_id, file_size) VALUES (?, ?, ?, ?)",
                (normalized_path, media_type, album_id, file_size)
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

    def get_total_media_count(self, active_album_id) -> int:
        """Get the total number of media items in the database."""
        self.cursor.execute("SELECT COUNT(*) FROM media WHERE album_id = ?", (active_album_id,))
        return self.cursor.fetchone()[0]

    def get_rankings_page(self, page: int, per_page: int = 50, media_type: str = "all",
                          album_id: int = 1, sort_by: str = "rating", sort_order: str = "DESC") -> Tuple[
        List[tuple], int]:
        """
        Get a page of ranked media items with sorting options.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page
            media_type: Type of media to filter by (all, image, gif, video)
            album_id: ID of the album to filter by
            sort_by: Column to sort by (rating, votes, path, file_size)
            sort_order: Sort order (ASC or DESC)
        """
        # Validate and sanitize sort parameters
        valid_sort_columns = {
            'rating': 'rating',
            'votes': 'votes',
            'file_name': 'path',  # We'll sort by path for file name
            'file_size': 'file_size'
        }
        sort_column = valid_sort_columns.get(sort_by, 'rating')  # Default to rating if invalid
        sort_direction = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        # Get total count with filter
        if media_type == "all":
            self.cursor.execute(
                "SELECT COUNT(*) FROM media WHERE album_id = ?",
                (album_id,)
            )
        else:
            self.cursor.execute(
                "SELECT COUNT(*) FROM media WHERE type = ? AND album_id = ?",
                (media_type, album_id)
            )
        total_items = self.cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * per_page

        # Build the query
        query = """
            SELECT id, path, rating, votes 
            FROM media 
            WHERE {where_clause}
            ORDER BY {sort_column} {sort_direction}
            LIMIT ? OFFSET ?
        """

        # Set up where clause and parameters based on media type
        if media_type == "all":
            where_clause = "album_id = ?"
            params = (album_id, per_page, offset)
        else:
            where_clause = "type = ? AND album_id = ?"
            params = (media_type, album_id, per_page, offset)

        # Format and execute query
        formatted_query = query.format(
            where_clause=where_clause,
            sort_column=sort_column,
            sort_direction=sort_direction
        )

        self.cursor.execute(formatted_query, params)
        return self.cursor.fetchall(), total_items

    def get_pair_for_voting(self, album_id: int = 1) -> Tuple[Optional[tuple], Optional[tuple]]:
        """
        Get two media items for voting: one least voted and one random.

        Returns:
            Tuple of (least voted media, random media), where each is a tuple of
            (id, path, rating, votes) or None if not enough media items exist
        """
        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE album_id = ?
            ORDER BY votes ASC, RANDOM() 
            LIMIT 1
        """, (album_id,))
        least_voted = self.cursor.fetchone()

        if not least_voted:
            return None, None

        self.cursor.execute("""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE id != ? AND album_id = ?
            ORDER BY RANDOM() 
            LIMIT 1
        """, (least_voted[0], album_id))
        random_media = self.cursor.fetchone()

        return least_voted, random_media

    def close(self):
        """Close the database connection."""
        self.conn.close()