from datetime import datetime, timezone
from pathlib import Path
from secrets import randbelow
import sqlite3
from uuid import uuid4


class ChatDatabase:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS chat_groups ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL COLLATE NOCASE UNIQUE)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO chat_groups (id, name) VALUES (1, 'Study Room')"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    username TEXT PRIMARY KEY,
                    photo TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    photo TEXT,
                    selected_group_id INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id),
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    text TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    file_id TEXT,
                    file_name TEXT,
                    file_size INTEGER,
                    mime_type TEXT,
                    group_id INTEGER NOT NULL DEFAULT 1,
                    file_data BLOB,
                    user_id TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(messages)")
            }
            migrations = (
                ("file_id", "TEXT"),
                ("file_name", "TEXT"),
                ("file_size", "INTEGER"),
                ("mime_type", "TEXT"),
                ("group_id", "INTEGER NOT NULL DEFAULT 1"),
                ("user_id", "TEXT"),
                ("file_data", "BLOB"),
            )
            for name, declaration in migrations:
                if name not in columns:
                    connection.execute(
                        "ALTER TABLE messages ADD COLUMN {} {}".format(
                            name, declaration
                        )
                    )

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_group(self, name):
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO chat_groups (name) VALUES (?)", (name,)
                )
        except sqlite3.IntegrityError:
            return None
        return {"id": cursor.lastrowid, "name": name}

    def list_groups(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name FROM chat_groups ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_group(self, group_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name FROM chat_groups WHERE id = ?", (group_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def create_user(self, token_hash):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        user_id = uuid4().hex
        username = "Student-{:04d}".format(randbelow(10000))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO users (user_id, username, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, username, now, now),
            )
            connection.execute(
                "INSERT INTO user_sessions (token_hash, user_id, created_at) "
                "VALUES (?, ?, ?)",
                (token_hash, user_id, now),
            )
        return self.get_user(user_id)

    def get_user(self, user_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username, photo, selected_group_id "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_user_by_session(self, token_hash):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT users.user_id, users.username, users.photo, "
                "users.selected_group_id FROM users JOIN user_sessions "
                "ON user_sessions.user_id = users.user_id "
                "WHERE user_sessions.token_hash = ?",
                (token_hash,),
            ).fetchone()
        return dict(row) if row is not None else None

    def update_user(self, user_id, username=None, photo=None, selected_group_id=None):
        updates = []
        values = []
        if username is not None:
            updates.append("username = ?")
            values.append(str(username).strip()[:32])
        if photo is not None:
            updates.append("photo = ?")
            values.append(str(photo).strip() or None)
        if selected_group_id is not None:
            updates.append("selected_group_id = ?")
            values.append(selected_group_id)
        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
            values.append(user_id)
            with self._connect() as connection:
                connection.execute(
                    "UPDATE users SET {} WHERE user_id = ?".format(", ".join(updates)),
                    values,
                )
        return self.get_user(user_id)

    def delete_user(self, user_id):
        with self._connect() as connection:
            connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    def get_profile(self, username):
        username = str(username or "").strip()[:32]
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username, photo FROM profiles WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row is not None else None

    def save_profile(self, username, photo):
        username = str(username or "").strip()[:32]
        if not username:
            return None
        with self._connect() as connection:
            if photo:
                connection.execute(
                    "INSERT INTO profiles (username, photo, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(username) DO UPDATE SET photo = excluded.photo, "
                    "updated_at = excluded.updated_at",
                    (username, str(photo).strip(), datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
            else:
                connection.execute("DELETE FROM profiles WHERE username = ?", (username,))
        return self.get_profile(username)

    def save_message(self, user_id, username, text, group_id=1):
        sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (user_id, username, text, sent_at, group_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, text, sent_at, group_id),
            )
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "user_id": user_id,
            "username": username,
            "text": text,
            "sent_at": sent_at,
            "type": "text",
            "group_id": group_id,
        }

    def save_file_message(
        self, user_id, username, file_id, file_name, file_size, mime_type,
        file_data, group_id=1
    ):
        sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (user_id, username, text, sent_at, file_id, "
                "file_name, file_size, mime_type, group_id, file_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id, username, "", sent_at, file_id, file_name, file_size,
                    mime_type, group_id, file_data,
                ),
            )
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "user_id": user_id,
            "username": username,
            "text": "",
            "sent_at": sent_at,
            "type": "file",
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size,
            "mime_type": mime_type,
            "group_id": group_id,
        }

    def recent_messages(self, group_id=1, limit=50):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT messages.id,
                    COALESCE(users.username, messages.username) AS username,
                    messages.user_id, messages.text, messages.sent_at,
                    messages.file_id, messages.file_name, messages.file_size,
                    messages.mime_type, messages.group_id,
                    COALESCE(users.photo, profiles.photo) AS profile_photo
                FROM messages
                LEFT JOIN profiles ON profiles.username = messages.username
                LEFT JOIN users ON users.user_id = messages.user_id
                WHERE messages.group_id = ?
                ORDER BY messages.id DESC LIMIT ?
                """,
                (group_id, limit),
            ).fetchall()
        messages = [dict(row) for row in rows]
        for message in messages:
            message["type"] = "file" if message["file_id"] else "text"
        messages.reverse()
        return messages

    def find_file(self, file_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT file_id, file_name, file_size, mime_type, file_data "
                "FROM messages WHERE file_id = ? LIMIT 1",
                (file_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_message(self, message_id, user_id, group_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, user_id, group_id, file_id, file_name FROM messages "
                "WHERE id = ? AND user_id = ? AND group_id = ?",
                (message_id, user_id, group_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "DELETE FROM messages WHERE id = ? AND user_id = ? AND group_id = ?",
                (message_id, user_id, group_id),
            )
        return dict(row)