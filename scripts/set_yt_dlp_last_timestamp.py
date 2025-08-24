import os
import sys
import sqlite3


def main():
    target_iso = "2025-08-01T12:00:00"

    # Accept DB path via CLI argument or environment variable
    # Usage: python scripts/set_yt_dlp_last_timestamp.py <path_to_db>
    db_path = None
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    elif os.environ.get("MUSICPLAYER_DB_PATH"):
        db_path = os.environ["MUSICPLAYER_DB_PATH"]

    if not db_path:
        print("Error: Database path not provided.\n"
              "Pass it as an argument or set MUSICPLAYER_DB_PATH env var.\n"
              "Example: python scripts/set_yt_dlp_last_timestamp.py Z:/AAAAA01/MusicPlayerDirectory/playback_positions.db")
        sys.exit(1)

    if not os.path.exists(db_path):
        print(f"Error: DB not found: {db_path}")
        sys.exit(1)

    print(f"Using DB: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='yt_dlp_updates'
        """)
        if cur.fetchone() is None:
            print("yt_dlp_updates table not found in this database. Nothing to update.")
            return

        # Update both last_check_time and last_update_time so the 24h gate passes
        cur.execute(
            """
            UPDATE yt_dlp_updates
               SET last_check_time = ?,
                   last_update_time = ?,
                   updated_at = ?
            """,
            (target_iso, target_iso, target_iso),
        )
        affected = cur.rowcount
        conn.commit()
        print(f"Updated timestamps on {affected} record(s) to {target_iso}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()


