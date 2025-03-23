import sqlite3

def export_album(db, album_id: int, file_path: str):
    try:
        backup_conn = sqlite3.connect(file_path)
        backup_cursor = backup_conn.cursor()

        # Create tables in the backup database
        backup_cursor.execute("""
            CREATE TABLE albums (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at DATETIME,
                total_media INTEGER
            )
        """)
        backup_cursor.execute("""
            CREATE TABLE media (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                rating REAL,
                glicko_phi REAL,
                glicko_sigma REAL,
                votes INTEGER,
                type TEXT NOT NULL,
                album_id INTEGER,
                file_size INTEGER,
                FOREIGN KEY (album_id) REFERENCES albums (id),
                UNIQUE(path, album_id)
            )
        """)
        backup_cursor.execute("""
            CREATE TABLE votes (
                id INTEGER PRIMARY KEY,
                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,
                album_id INTEGER NOT NULL,
                timestamp DATETIME,
                FOREIGN KEY (winner_id) REFERENCES media (id),
                FOREIGN KEY (loser_id) REFERENCES media (id),
                FOREIGN KEY (album_id) REFERENCES albums (id)
            )
        """)

        # Export album data
        album_data = db.cursor.execute(
            "SELECT id, name, created_at, total_media FROM albums WHERE id = ?",
            (album_id,)
        ).fetchone()
        backup_cursor.execute(
            "INSERT INTO albums VALUES (?, ?, ?, ?)", album_data
        )

        # Export media data
        media_data = db.cursor.execute(
            """SELECT id, path, rating, glicko_phi, glicko_sigma, votes, type, album_id, file_size 
            FROM media WHERE album_id = ?""",
            (album_id,)
        ).fetchall()
        for media in media_data:
            backup_cursor.execute(
                "INSERT INTO media VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", media
            )

        # Export votes data
        votes_data = db.cursor.execute(
            "SELECT * FROM votes WHERE album_id = ?",
            (album_id,)
        ).fetchall()
        for vote in votes_data:
            backup_cursor.execute(
                "INSERT INTO votes VALUES (?, ?, ?, ?, ?)", vote
            )

        backup_conn.commit()
        backup_conn.close()
        return True
    except Exception as e:
        raise e

def import_album(db, file_path: str, new_name: str = None):
    try:
        backup_conn = sqlite3.connect(file_path)
        backup_cursor = backup_conn.cursor()

        # Fetch backup album data
        backup_cursor.execute("SELECT * FROM albums")
        backup_album = backup_cursor.fetchone()
        if not backup_album:
            return False, "No album found in backup."

        # Check for existing album name
        original_name = backup_album[1]
        new_name = new_name or original_name
        existing = db.cursor.execute(
            "SELECT id FROM albums WHERE name = ?",
            (new_name,)
        ).fetchone()
        if existing:
            return False, "Album name already exists."

        # Create new album with original timestamp
        db.cursor.execute(
            "INSERT INTO albums (name, created_at, total_media) VALUES (?, ?, ?)",
            (new_name, backup_album[2], backup_album[3])
        )
        new_album_id = db.cursor.lastrowid

        # Import media and map old IDs to new IDs
        media_id_map = {}
        backup_cursor.execute("SELECT * FROM media WHERE album_id = ?", (backup_album[0],))
        for media in backup_cursor.fetchall():
            old_id = media[0]
            db.cursor.execute(
                """INSERT INTO media 
                (path, rating, glicko_phi, glicko_sigma, votes, type, album_id, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (media[1], media[2], media[3], media[4], media[5], media[6], new_album_id, media[8])
            )
            media_id_map[old_id] = db.cursor.lastrowid

        # Import votes with updated media IDs
        backup_cursor.execute("SELECT * FROM votes WHERE album_id = ?", (backup_album[0],))
        for vote in backup_cursor.fetchall():
            new_winner = media_id_map.get(vote[1])
            new_loser = media_id_map.get(vote[2])
            if new_winner and new_loser:
                db.cursor.execute(
                    "INSERT INTO votes (winner_id, loser_id, album_id, timestamp) VALUES (?, ?, ?, ?)",
                    (new_winner, new_loser, new_album_id, vote[4])
                )

        db.conn.commit()
        backup_conn.close()
        return True, "Album imported successfully."
    except Exception as e:
        return False, str(e)