# db/database.py
import logging
import os
import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional

from core.reliability_calculator import ReliabilityCalculator

logger = logging.getLogger(__name__)


def get_database_path():
    """Determine a writable path for the database."""
    if os.name == "nt":  # Windows
        db_dir = Path(os.getenv("LOCALAPPDATA")) / "KuraApp"
    else:  # Linux/macOS
        db_dir = Path.home() / ".kuraapp"

    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "media_ratings.db")

class Database:
    def __init__(self, db_path: str = None):
        """
        Initialize database connection and create tables if they don't exist.

        Args:
            db_path: Path to the SQLite database file (optional)
        """
        self.db_path = db_path or get_database_path()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._update_schema()
        self._create_indices()
        self._ensure_default_album()

        self.last_pairs = {}

    def _create_indices(self):
        """Create indices for efficient sorting and filtering."""
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_media_rating ON media (rating)",
            "CREATE INDEX IF NOT EXISTS idx_media_votes ON media (votes)",
            "CREATE INDEX IF NOT EXISTS idx_media_path ON media (path)",  # For filename sorting
            "CREATE INDEX IF NOT EXISTS idx_media_file_size ON media (file_size)",
            "CREATE INDEX IF NOT EXISTS idx_media_type ON media (type)",  # Already existed
            "CREATE INDEX IF NOT EXISTS idx_media_album ON media (album_id)",  # For album filtering
            "CREATE INDEX IF NOT EXISTS idx_media_glicko_phi ON media (glicko_phi)",
            "CREATE INDEX IF NOT EXISTS idx_votes_album ON votes (album_id)",
            "CREATE INDEX IF NOT EXISTS idx_votes_winner ON votes (winner_id)",
            "CREATE INDEX IF NOT EXISTS idx_votes_loser ON votes (loser_id)",
            "CREATE INDEX IF NOT EXISTS idx_votes_pair ON votes (album_id, winner_id, loser_id)",
            "CREATE INDEX IF NOT EXISTS idx_media_created_at ON media (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_media_modified_at ON media (modified_at)"
        ]

        for index in indices:
            self.cursor.execute(index)
        self.conn.commit()

    def _update_schema(self):
        """Check and update the database schema if necessary."""
        try:
            # Check for 'created_at' column in 'media' table
            self.cursor.execute("PRAGMA table_info(media)")
            columns = [info[1] for info in self.cursor.fetchall()]
            
            if 'created_at' not in columns:
                logger.info("Adding 'created_at' column to 'media' table.")
                # Add column without default first
                self.cursor.execute("ALTER TABLE media ADD COLUMN created_at DATETIME")
                # Update existing rows with current timestamp
                self.cursor.execute("UPDATE media SET created_at = datetime('now') WHERE created_at IS NULL")
                self.conn.commit()
            
            if 'modified_at' not in columns:
                logger.info("Adding 'modified_at' column to 'media' table.")
                self.cursor.execute("ALTER TABLE media ADD COLUMN modified_at DATETIME")
                self.conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Error updating schema: {e}")
            # Depending on the severity, you might want to raise the exception
            # or handle it more gracefully, e.g., by notifying the user.
            raise # Re-raise the exception to halt initialization if schema update fails

    def _create_tables(self):
        """Create necessary database tables if they don't exist."""
        # Albums table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_media INTEGER DEFAULT 0,
                rating_system TEXT DEFAULT 'glicko2'
            )
        """)

        # Media table with album support
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                rating REAL DEFAULT 1200,
                glicko_phi REAL DEFAULT 350,
                glicko_sigma REAL DEFAULT 0.06,
                votes INTEGER DEFAULT 0,
                type TEXT NOT NULL,
                album_id INTEGER NOT NULL,
                file_size INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                modified_at DATETIME,
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
                album_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (winner_id) REFERENCES media (id),
                FOREIGN KEY (loser_id) REFERENCES media (id),
                FOREIGN KEY (album_id) REFERENCES albums (id)
            )
        """)

        self.conn.commit()

    def _ensure_default_album(self):
        """Ensure default album exists"""
        self.cursor.execute("""
            INSERT OR IGNORE INTO albums (id, name) VALUES (1, 'Default')
        """)
        self.conn.commit()

    def create_album(self, name: str, rating_system: str = "glicko2") -> int:
        try:
            self.cursor.execute(
                "INSERT INTO albums (name, rating_system) VALUES (?, ?)",
                (name, rating_system)
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

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
        """Delete an album and all its media. If deleting the default album (id=1), creates a new one."""
        try:
            was_default = album_id == 1

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

            # If we just deleted the default album, create a new one
            if was_default:
                self.cursor.execute("""
                    INSERT INTO albums (id, name, created_at)
                    VALUES (1, 'Default', datetime('now'))
                """)

            self.conn.commit()
            return True

        except Exception as e:
            self.conn.rollback()
            logger.warning(f"Error deleting album: {e}")
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
            # Get the file modification time
            modified_time = os.path.getmtime(normalized_path)

            ext = Path(file_path).suffix.lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                media_type = 'image'
            elif ext == '.gif':
                media_type = 'gif'
            elif ext in ['.mp4', '.avi', '.m4v', '.wmv', '.mov', '.mkv', '.webm']:
                media_type = 'video'

            # Check if the file already exists in the database
            self.cursor.execute(
                "SELECT id FROM media WHERE path = ? AND album_id = ?",
                (normalized_path, album_id)
            )
            if self.cursor.fetchone():
                return False

            self.cursor.execute(
                "INSERT INTO media (path, type, album_id, file_size, modified_at) VALUES (?, ?, ?, ?, ?)",
                (normalized_path, media_type, album_id, file_size, modified_time)
            )

            # Increment total_media for the album
            self.cursor.execute(
                "UPDATE albums SET total_media = total_media + 1 WHERE id = ?",
                (album_id,)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def _recalculate_ratings(self):
        # Get all albums
        albums = self.get_albums()
        for album in albums:
            album_id = album[0]
            rating_system = self.get_album_rating_system(album_id)

            if rating_system == "elo":
                self._recalculate_elo(album_id)
            else:
                self._recalculate_glicko2(album_id)

    def get_album_rating_system(self, album_id: int) -> str:
        """Get the rating system used by an album"""
        self.cursor.execute("SELECT rating_system FROM albums WHERE id = ?", (album_id,))
        result = self.cursor.fetchone()
        return result[0] if result else "glicko2"

    def _recalculate_elo(self, album_id: int):

        from core.elo import Rating

        # Reset all ratings
        self.cursor.execute("UPDATE media SET rating = 1200, votes = 0")
        self.conn.commit()

        # Process votes per album
        albums = self.get_albums()
        for album in albums:
            album_id = album[0]
            media_count = self.get_total_media_count(album_id)

            self.cursor.execute("""
                        SELECT winner_id, loser_id 
                        FROM votes 
                        WHERE album_id = ?
                        ORDER BY timestamp ASC
                    """, (album_id,))
            votes = self.cursor.fetchall()

            ratings = {row[0]: 1200 for row in
                       self.cursor.execute("SELECT id FROM media WHERE album_id = ?", (album_id,))}

            # Process each vote with historical context
            for idx, (winner_id, loser_id) in enumerate(votes):
                if winner_id not in ratings or loser_id not in ratings:
                    continue

                v = idx + 1
                reliability = ReliabilityCalculator.calculate_reliability(
                    media_count, v, rating_system="elo"
                )
                k_factor = 32 if reliability < 85 else 16

                rating = Rating(
                    ratings[winner_id],
                    ratings[loser_id],
                    Rating.WIN,
                    Rating.LOST,
                    k_factor
                )
                new_ratings = rating.get_new_ratings()
                ratings[winner_id] = new_ratings['a']
                ratings[loser_id] = new_ratings['b']

                self.cursor.execute("""
                            UPDATE media 
                            SET votes = votes + 1 
                            WHERE id IN (?, ?)
                        """, (winner_id, loser_id))

            # Update final ratings
            for media_id, rating in ratings.items():
                self.cursor.execute("""
                            UPDATE media SET rating = ? WHERE id = ?
                        """, (rating, media_id))

        self.conn.commit()

    def _recalculate_glicko2(self, album_id: int):
        from core.glicko2 import Glicko2Rating

        # Reset all Glicko2 parameters and vote counts for this album
        self.cursor.execute("""
            UPDATE media 
            SET rating = 1200,
                glicko_phi = 350,
                glicko_sigma = 0.06,
                votes = 0
            WHERE album_id = ?
        """, (album_id,))

        # Get all media IDs in this album
        media = {}
        vote_counts = {}
        self.cursor.execute("SELECT id FROM media WHERE album_id = ?", (album_id,))
        for (media_id,) in self.cursor.fetchall():
            media[media_id] = (1200.0, 350.0, 0.06)  # (mu, phi, sigma)
            vote_counts[media_id] = 0

        # Process votes in chronological order
        self.cursor.execute("""
            SELECT winner_id, loser_id 
            FROM votes 
            WHERE album_id = ?
            ORDER BY timestamp ASC
        """, (album_id,))

        for winner_id, loser_id in self.cursor.fetchall():
            if winner_id not in media or loser_id not in media:
                continue

            # Get current parameters
            w_mu, w_phi, w_sigma = media[winner_id]
            l_mu, l_phi, l_sigma = media[loser_id]

            # Calculate updates
            gr = Glicko2Rating(
                w_mu, w_phi, w_sigma,
                l_mu, l_phi, l_sigma,
                1.0, 0.0  # Winner gets 1.0, loser 0.0
            )
            new_ratings = gr.get_new_ratings()

            # Update in-memory state
            media[winner_id] = (
                new_ratings['a']['mu'],
                new_ratings['a']['phi'],
                new_ratings['a']['sigma']
            )
            media[loser_id] = (
                new_ratings['b']['mu'],
                new_ratings['b']['phi'],
                new_ratings['b']['sigma']
            )
            vote_counts[winner_id] += 1
            vote_counts[loser_id] += 1

        # Save final ratings and recomputed vote counts
        for media_id, (mu, phi, sigma) in media.items():
            self.cursor.execute("""
                UPDATE media SET
                    rating = ?,
                    glicko_phi = ?,
                    glicko_sigma = ?,
                    votes = ?
                WHERE id = ?
            """, (mu, phi, sigma, vote_counts[media_id], media_id))

        self.conn.commit()


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
            # Get media path and album_id
            self.cursor.execute("SELECT path, album_id FROM media WHERE id = ?", (media_id,))
            result = self.cursor.fetchone()
            if not result:
                return None
            media_path, album_id = result

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

            self.cursor.execute(
                "UPDATE albums SET total_media = total_media - 1 WHERE id = ?",
                (album_id,)
            )

            # Commit transaction
            self.conn.commit()

            # Return path for file deletion
            return media_path if media_path else None

        except Exception as e:
            self.conn.rollback()
            raise e

    def update_ratings(self, winner_id: int, loser_id: int, album_id: int, weight: int = 1):
        """
        Update ratings after a vote. Handles both ELO and Glicko2 systems.

        Args:
            winner_id: Winning media ID
            loser_id: Losing media ID
            album_id: Album containing the pair
            weight: Conviction strength (1 = normal vote, 2 = double vote).
                    Applies a stronger rating update but records a single vote edge.
        """
        weight = max(1, int(weight))
        try:
            self.conn.execute("BEGIN")

            # Get rating system from album
            rating_system = self.get_album_rating_system(album_id)

            if rating_system == "elo":
                # ELO SYSTEM ======================================================
                # Get current ratings
                self.cursor.execute("SELECT rating FROM media WHERE id = ?", (winner_id,))
                winner_rating = self.cursor.fetchone()[0]
                self.cursor.execute("SELECT rating FROM media WHERE id = ?", (loser_id,))
                loser_rating = self.cursor.fetchone()[0]

                # Calculate ELO updates
                from core.elo import Rating
                n = self.get_total_media_count(album_id)
                v = self.get_total_votes(album_id)
                mean_phi = None
                reliability = ReliabilityCalculator.calculate_reliability(
                    n, v + 1, rating_system=rating_system, mean_phi=mean_phi
                )
                k_factor = (32 if reliability < 85 else 16) * weight

                elo = Rating(winner_rating, loser_rating,
                             Rating.WIN, Rating.LOST, k_factor)
                new_ratings = elo.get_new_ratings()

                # Update winner
                self.cursor.execute("""
                    UPDATE media 
                    SET rating = ?, votes = votes + 1 
                    WHERE id = ?
                """, (new_ratings['a'], winner_id))

                # Update loser
                self.cursor.execute("""
                    UPDATE media 
                    SET rating = ?, votes = votes + 1 
                    WHERE id = ?
                """, (new_ratings['b'], loser_id))

            else:
                # GLICKO2 SYSTEM ==================================================
                from core.glicko2 import Glicko2Rating

                # Get current Glicko2 parameters for both items
                self.cursor.execute("""
                    SELECT rating, glicko_phi, glicko_sigma 
                    FROM media 
                    WHERE id IN (?, ?)
                    ORDER BY CASE WHEN id = ? THEN 1 ELSE 2 END
                """, (winner_id, loser_id, winner_id))

                winner_mu, winner_phi, winner_sigma = self.cursor.fetchone()
                loser_mu, loser_phi, loser_sigma = self.cursor.fetchone()

                # Apply a stronger update for weight>1 without inserting rematch rows
                new_a = {'mu': winner_mu, 'phi': winner_phi, 'sigma': winner_sigma}
                new_b = {'mu': loser_mu, 'phi': loser_phi, 'sigma': loser_sigma}
                for _ in range(weight):
                    gr = Glicko2Rating(
                        mu_a=new_a['mu'], phi_a=new_a['phi'], sigma_a=new_a['sigma'],
                        mu_b=new_b['mu'], phi_b=new_b['phi'], sigma_b=new_b['sigma'],
                        score_a=1.0, score_b=0.0
                    )
                    updated = gr.get_new_ratings()
                    new_a, new_b = updated['a'], updated['b']

                # Update winner
                self.cursor.execute("""
                    UPDATE media SET
                        rating = ?,
                        glicko_phi = ?,
                        glicko_sigma = ?,
                        votes = votes + 1
                    WHERE id = ?
                """, (
                    new_a['mu'],
                    new_a['phi'],
                    new_a['sigma'],
                    winner_id
                ))

                # Update loser
                self.cursor.execute("""
                    UPDATE media SET
                        rating = ?,
                        glicko_phi = ?,
                        glicko_sigma = ?,
                        votes = votes + 1
                    WHERE id = ?
                """, (
                    new_b['mu'],
                    new_b['phi'],
                    new_b['sigma'],
                    loser_id
                ))

            # Record a single vote edge (even for weighted/double votes)
            self.cursor.execute("""
                INSERT INTO votes (winner_id, loser_id, album_id)
                VALUES (?, ?, ?)
            """, (winner_id, loser_id, album_id))

            self.conn.commit()

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error updating ratings: {str(e)}")
            raise e

    def get_mean_glicko_phi(self, album_id: int) -> Optional[float]:
        """Average Glicko RD (phi) for an album, or None if empty."""
        self.cursor.execute(
            "SELECT AVG(glicko_phi) FROM media WHERE album_id = ?",
            (album_id,)
        )
        result = self.cursor.fetchone()
        if result is None or result[0] is None:
            return None
        return float(result[0])

    def get_total_votes(self, album_id: int) -> int:
        """Get total number of votes cast in an album."""
        self.cursor.execute("SELECT COUNT(*) FROM votes WHERE album_id = ?", (album_id,))
        return self.cursor.fetchone()[0]

    def get_total_media_count(self, active_album_id) -> int:
        """Get the total number of media items in the database."""
        self.cursor.execute("SELECT COUNT(*) FROM media WHERE album_id = ?", (active_album_id,))
        return self.cursor.fetchone()[0]

    def get_media_type_counts(self, album_id: int) -> dict:
        """Get media type counts and total size for an album."""
        self.cursor.execute("""
            SELECT 
                type,
                COUNT(*) as count,
                SUM(file_size) as total_size
            FROM media 
            WHERE album_id = ?
            GROUP BY type
        """, (album_id,))

        result = {
            'image': 0,
            'gif': 0,
            'video': 0,
            'total_size': 0
        }

        for row in self.cursor.fetchall():
            media_type = row[0]
            result[media_type] = row[1]
            result['total_size'] += row[2]

        return result

    def find_missing_media(self, album_id: Optional[int] = None) -> List[dict]:
        """
        Find media entries where the file doesn't exist.

        Args:
            album_id: If given, only check media in this album; otherwise check all albums.
        """
        rows = self.get_media_paths_for_scan(album_id)
        missing = []
        for media_id, path, file_size in rows:
            if not os.path.exists(path):
                missing.append({
                    'id': media_id,
                    'original_path': path,
                    'filename': os.path.basename(path),
                    'file_size': file_size
                })
        return missing

    def get_media_paths_for_scan(self, album_id: Optional[int] = None) -> List[tuple]:
        """Get (id, path, file_size) rows for existence checks, optionally scoped to an album."""
        if album_id is None:
            self.cursor.execute("SELECT id, path, file_size FROM media")
        else:
            self.cursor.execute(
                "SELECT id, path, file_size FROM media WHERE album_id = ?",
                (album_id,)
            )
        return self.cursor.fetchall()

    def get_media_path(self, media_id: int) -> Optional[str]:
        """Get the file path for a media item by its ID."""
        self.cursor.execute("SELECT path FROM media WHERE id = ?", (media_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def update_media_path(self, media_id: int, new_path: str) -> bool:
        """Update a media file's path, refreshing file size and modification time."""
        try:
            normalized_path = str(Path(new_path).resolve())
            try:
                file_size = os.path.getsize(normalized_path)
                modified_time = os.path.getmtime(normalized_path)
            except OSError:
                file_size = None
                modified_time = None

            if file_size is not None:
                self.cursor.execute(
                    "UPDATE media SET path = ?, file_size = ?, modified_at = ? WHERE id = ?",
                    (normalized_path, file_size, modified_time, media_id)
                )
            else:
                self.cursor.execute(
                    "UPDATE media SET path = ? WHERE id = ?",
                    (normalized_path, media_id)
                )
            self.conn.commit()
            return True
        except Exception as e:
            logger.warning(f"Error updating path: {e}")
            return False

    def delete_media_batch(self, media_ids: List[int], recalculate: bool = True) -> int:
        """
        Delete multiple media records (and their votes) in a single transaction,
        with at most one rating recalculation at the end.

        Args:
            media_ids: IDs of the media records to delete
            recalculate: Whether to recalculate ratings after deletion

        Returns:
            int: Number of media records actually deleted
        """
        if not media_ids:
            return 0
        try:
            self.conn.execute("BEGIN")

            placeholders = ",".join(["?"] * len(media_ids))
            self.cursor.execute(
                f"SELECT id, album_id FROM media WHERE id IN ({placeholders})",
                media_ids
            )
            rows = self.cursor.fetchall()
            if not rows:
                self.conn.rollback()
                return 0

            existing_ids = [row[0] for row in rows]
            existing_placeholders = ",".join(["?"] * len(existing_ids))

            self.cursor.execute(
                f"""
                DELETE FROM votes
                WHERE winner_id IN ({existing_placeholders})
                OR loser_id IN ({existing_placeholders})
                """,
                existing_ids + existing_ids
            )

            self.cursor.execute(
                f"DELETE FROM media WHERE id IN ({existing_placeholders})",
                existing_ids
            )

            # Decrement album counters by the number of deletions per album
            album_counts = {}
            for _, album_id in rows:
                album_counts[album_id] = album_counts.get(album_id, 0) + 1
            for album_id, count in album_counts.items():
                self.cursor.execute(
                    "UPDATE albums SET total_media = total_media - ? WHERE id = ?",
                    (count, album_id)
                )

            if recalculate:
                self._recalculate_ratings()

            self.conn.commit()
            return len(existing_ids)

        except Exception as e:
            self.conn.rollback()
            raise e

    def get_albums_page(self, page: int, per_page: int, sort_by: str = "name", sort_order: str = "ASC") -> Tuple[
        List[tuple], int]:
        valid_columns = {"id", "name", "total_media", "rating_system", "created_at"}
        sort_by = sort_by if sort_by in valid_columns else "name"
        sort_order = sort_order.upper() if sort_order.upper() in ("ASC", "DESC") else "ASC"

        offset = (page - 1) * per_page
        query = f"""
            SELECT id, name, total_media, created_at, rating_system
            FROM albums
            ORDER BY {sort_by} {sort_order}
            LIMIT ? OFFSET ?
        """
        self.cursor.execute(query, (per_page, offset))
        albums = self.cursor.fetchall()

        self.cursor.execute("SELECT COUNT(*) FROM albums")
        total = self.cursor.fetchone()[0]
        return albums, total

    def get_rankings_page(self, page: int, per_page: int = 50, media_type: str = "all",
                          album_id: int = 1, sort_by: str = "rating", sort_order: str = "DESC",
                          search_query: str = None) -> Tuple[List[tuple], int]:
        """
        Get a page of ranked media items with sorting and search options.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page
            media_type: Type of media to filter by (all, image, gif, video)
            album_id: ID of the album to filter by
            sort_by: Column to sort by (rating, votes, path, file_size)
            sort_order: Sort order (ASC or DESC)
            search_query: Search string to filter by filename
        """
        # Validate and sanitize sort parameters
        valid_sort_columns = {
            'rating': 'rating',
            'votes': 'votes',
            'file_name': 'path',  # Sort by path for file name
            'file_size': 'file_size',
            'created_at': 'created_at',
            'modified_at': 'modified_at'
        }
        sort_column = valid_sort_columns.get(sort_by, 'rating')
        sort_direction = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        # Build query components
        where_clauses = ["album_id = ?"]
        params = [album_id]

        # Media type filter
        if media_type != "all":
            where_clauses.append("type = ?")
            params.append(media_type)

        # Search filter
        if search_query:
            where_clauses.append("(path LIKE ?)")
            params.append(f"%{search_query}%")

        # Combine WHERE clauses
        where_statement = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_query = f"""
            SELECT COUNT(*) 
            FROM media 
            WHERE {where_statement}
        """
        self.cursor.execute(count_query, params)
        total_items = self.cursor.fetchone()[0]

        # Build main query
        query = f"""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE {where_statement}
            ORDER BY {sort_column} {sort_direction}
            LIMIT ? OFFSET ?
        """

        # Add pagination parameters
        offset = (page - 1) * per_page
        params.extend([per_page, offset])

        # Execute query
        self.cursor.execute(query, params)
        return self.cursor.fetchall(), total_items

    def get_vote_history_page(self, album_id: int, page: int, per_page: int,
                              sort_by: str = "timestamp", sort_order: str = "DESC",
                              search_query: str = None) -> Tuple[List[tuple], int]:
        """Get paginated vote history with sorting and filtering."""
        valid_sort = {
            "timestamp": "v.timestamp",
            "winner": "winner_path",
            "loser": "loser_path"
        }
        sort_column = valid_sort.get(sort_by, "v.timestamp")

        base_query = """
            SELECT 
                v.id,
                v.timestamp,
                winner.path as winner_path,
                loser.path as loser_path
            FROM votes v
            JOIN media winner ON v.winner_id = winner.id
            JOIN media loser ON v.loser_id = loser.id
            WHERE v.album_id = ?
        """
        params = [album_id]

        if search_query:
            base_query += " AND (winner.path LIKE ? OR loser.path LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])

        # Get total count
        count_query = f"SELECT COUNT(*) FROM ({base_query})"
        self.cursor.execute(count_query, params)
        total = self.cursor.fetchone()[0]

        # Add sorting and pagination
        base_query += f" ORDER BY {sort_column} {sort_order} LIMIT ? OFFSET ?"
        offset = (page - 1) * per_page
        params.extend([per_page, offset])

        self.cursor.execute(base_query, params)
        return self.cursor.fetchall(), total

    def delete_votes(self, vote_ids: List[int]):
        """Delete multiple votes and recalculate ratings once"""
        try:
            self.conn.execute("BEGIN")
            # Delete votes
            self.cursor.executemany("DELETE FROM votes WHERE id = ?", [(vid,) for vid in vote_ids])
            # Recalculate ratings
            self._recalculate_ratings()
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            raise e

    def get_pair_for_voting(self, album_id: int = 1) -> Tuple[Optional[tuple], Optional[tuple]]:
        """
        Get a high-information voting pair.

        Primary item: high Glicko uncertainty (phi) then least-voted for Glicko
        albums; least-voted for Elo. Opponent: always rating-nearby, preferring
        uncertain / under-voted items, excluding previously compared edges when
        alternatives exist.
        """
        media_count = self.get_total_media_count(album_id)
        if media_count < 2:
            return None, None

        rating_system = self.get_album_rating_system(album_id)
        first_item = self._get_primary_item(album_id, rating_system)
        if not first_item:
            return None, None

        second_item = self._get_second_item(album_id, first_item, rating_system)
        if not second_item:
            return None, None

        self.last_pairs[album_id] = (first_item[0], second_item[0])
        return first_item, second_item

    def _get_primary_item(self, album_id: int, rating_system: str):
        """Pick the most informative under-compared item for this album."""
        exclude_ids = list(self.last_pairs.get(album_id, ()))

        exclude_clause = ""
        params = [album_id]
        if exclude_ids:
            placeholders = ",".join(["?"] * len(exclude_ids))
            exclude_clause = f"AND id NOT IN ({placeholders})"
            params += exclude_ids

        if rating_system == "elo":
            order_clause = "votes ASC, RANDOM()"
        else:
            # Prefer uncertain (high phi), then under-voted
            order_clause = "glicko_phi DESC, votes ASC, RANDOM()"

        query = f"""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE album_id = ?
            {exclude_clause}
            ORDER BY {order_clause}
            LIMIT 1
        """
        self.cursor.execute(query, params)
        return self.cursor.fetchone()

    def _rematch_exclusion_sql(self, first_id: int):
        """
        SQL fragment excluding media already compared with first_id in this album.
        Caller must append album_id, first_id, first_id to params (in that order
        relative to the placeholders below — see _get_second_item).
        """
        return """
            AND NOT EXISTS (
                SELECT 1 FROM votes v
                WHERE v.album_id = ?
                  AND (
                    (v.winner_id = ? AND v.loser_id = media.id)
                    OR (v.winner_id = media.id AND v.loser_id = ?)
                  )
            )
        """

    def _get_second_item(self, album_id: int, first_item: tuple, rating_system: str):
        """
        Pick an informative opponent: rating-nearby, prefer high uncertainty /
        low votes, avoid rematches when possible.
        """
        exclude_ids = list(self.last_pairs.get(album_id, ()))
        exclude_ids.append(first_item[0])

        exclude_clause = ""
        base_params = [first_item[0], album_id]
        if exclude_ids:
            placeholders = ",".join(["?"] * len(exclude_ids))
            exclude_clause = f"AND id NOT IN ({placeholders})"
            base_params += exclude_ids

        rematch_sql = self._rematch_exclusion_sql(first_item[0])

        if rating_system == "elo":
            order_tiebreak = "votes ASC, RANDOM()"
        else:
            order_tiebreak = "glicko_phi DESC, votes ASC, RANDOM()"

        # Try with rematch exclusion first, then allow rematches as fallback
        for avoid_rematches in (True, False):
            for max_diff in (100, 200, None):
                rating_clause = ""
                params = list(base_params)

                if max_diff is not None:
                    rating_clause = "AND ABS(rating - ?) <= ?"
                    params += [first_item[2], max_diff]

                rematch_clause = ""
                if avoid_rematches:
                    rematch_clause = rematch_sql
                    params += [album_id, first_item[0], first_item[0]]

                # ORDER BY placeholder must be bound after WHERE placeholders
                order_clause = f"ABS(rating - ?) ASC, {order_tiebreak}"
                params += [first_item[2]]

                query = f"""
                    SELECT id, path, rating, votes 
                    FROM media 
                    WHERE id != ? 
                    AND album_id = ?
                    {exclude_clause}
                    {rating_clause}
                    {rematch_clause}
                    ORDER BY {order_clause}
                    LIMIT 1
                """
                self.cursor.execute(query, params)
                result = self.cursor.fetchone()
                if result:
                    return result

        # Absolute fallback
        query = f"""
            SELECT id, path, rating, votes 
            FROM media 
            WHERE id != ? 
            AND album_id = ?
            {exclude_clause}
            ORDER BY RANDOM() 
            LIMIT 1
        """
        self.cursor.execute(query, base_params)
        return self.cursor.fetchone()

    def close(self):
        """Close the database connection."""
        self.conn.close()