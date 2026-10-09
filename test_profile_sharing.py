import unittest
import sqlite3
import tempfile
from base64 import b64encode
from io import BytesIO
from uuid import uuid4
from pathlib import Path

import server
from database import ChatDatabase
from server import app


class ProfileSharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.original_database = server.database
        cls.original_profile_image_dir = getattr(server, "PROFILE_IMAGE_DIR", None)
        server.database = ChatDatabase(Path(cls.temp_dir.name) / "test.db")
        server.PROFILE_IMAGE_DIR = Path(cls.temp_dir.name) / "uploads" / "profiles"

    @classmethod
    def tearDownClass(cls):
        server.database = cls.original_database
        if cls.original_profile_image_dir is None:
            del server.PROFILE_IMAGE_DIR
        else:
            server.PROFILE_IMAGE_DIR = cls.original_profile_image_dir
        cls.temp_dir.cleanup()

    def test_user_profile_and_messages_are_database_backed(self):
        owner = app.test_client()
        viewer = app.test_client()
        photo = "data:image/jpeg;base64,abc123"

        owner_profile = owner.get("/api/me")
        self.assertEqual(owner_profile.status_code, 200, owner_profile.get_data(as_text=True))
        owner_cookie = owner.get_cookie("chat_user")
        self.assertIsNotNone(owner_cookie)
        self.assertNotIn(owner_profile.get_json()["username"], owner_cookie.value)
        self.assertTrue(owner_cookie.http_only)

        created_group = owner.post(
            "/api/groups", json={"name": "Test " + uuid4().hex[:8]}
        )
        self.assertEqual(created_group.status_code, 201)
        group_id = created_group.get_json()["group"]["id"]

        username = "Profile-" + uuid4().hex[:12]
        updated = owner.put(
            "/api/me",
            json={"username": username, "photo": photo, "group_id": group_id},
        )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        self.assertEqual(updated.get_json()["username"], username)
        self.assertEqual(updated.get_json()["photo"], photo)
        self.assertEqual(updated.get_json()["selected_group_id"], group_id)

        message = owner.post(
            "/api/messages",
            json={
                "username": "Impersonated user",
                "group_id": 999,
                "text": "Profile photo check",
            },
        )
        self.assertEqual(message.status_code, 201, message.get_data(as_text=True))
        self.assertEqual(message.get_json()["message"]["username"], username)
        persisted = owner.get("/api/me").get_json()
        self.assertEqual(persisted["username"], username)
        self.assertEqual(persisted["photo"], photo)

        viewer_profile = viewer.get("/api/me")
        self.assertEqual(viewer_profile.status_code, 200, viewer_profile.get_data(as_text=True))
        self.assertNotEqual(viewer_profile.get_json()["username"], username)

        viewer.put("/api/me", json={"group_id": group_id})
        state = viewer.get("/api/chat")
        self.assertEqual(state.status_code, 200, state.get_data(as_text=True))
        shared_message = next(
            item for item in state.get_json()["messages"]
            if item["id"] == message.get_json()["message"]["id"]
        )
        self.assertEqual(shared_message["username"], username)
        self.assertEqual(shared_message["profile_photo"], photo)

        deleted = owner.delete("/api/me")
        self.assertEqual(deleted.status_code, 204)
        replacement = owner.get("/api/me").get_json()
        self.assertNotEqual(replacement["user_id"], owner_profile.get_json()["user_id"])
        self.assertIsNone(replacement["photo"])

    def test_existing_message_database_migrates_without_losing_history(self):
        database_path = Path(self.temp_dir.name) / "legacy.db"
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "CREATE TABLE messages ("
                "id INTEGER PRIMARY KEY, username TEXT NOT NULL, text TEXT NOT NULL, "
                "sent_at TEXT NOT NULL, group_id INTEGER NOT NULL DEFAULT 1)"
            )
            connection.execute(
                "INSERT INTO messages (username, text, sent_at) "
                "VALUES ('Legacy User', 'kept message', '2026-09-30T00:00:00+00:00')"
            )

        database = ChatDatabase(database_path)
        columns = {row["name"] for row in database._connect().execute("PRAGMA table_info(messages)")}
        self.assertIn("user_id", columns)
        self.assertIn("file_data", columns)
        history = database.recent_messages(1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["text"], "kept message")
        self.assertEqual(history[0]["username"], "Legacy User")

    def test_uploaded_file_contents_are_stored_in_database(self):
        client = app.test_client()
        client.get("/api/me")
        file_bytes = b"stored in sqlite"
        response = client.post(
            "/upload",
            data={"file": (BytesIO(file_bytes), "notes.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        file_id = response.get_json()["message"]["file_id"]
        metadata = server.database.find_file(file_id)
        self.assertEqual(metadata["file_data"], file_bytes)
        self.assertEqual(client.get(f"/files/{file_id}/view").data, file_bytes)
        self.assertEqual(client.get(f"/files/{file_id}/download").data, file_bytes)

    def test_profile_photo_is_written_to_host_profiles_directory(self):
        client = app.test_client()
        user = client.get("/api/me").get_json()
        image_bytes = b"\xff\xd8\xff\xd9"
        photo = "data:image/jpeg;base64," + b64encode(image_bytes).decode("ascii")
        response = client.put("/api/me", json={"photo": photo})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        image_path = server.PROFILE_IMAGE_DIR / (user["user_id"] + ".jpg")
        self.assertTrue(image_path.is_file())
        self.assertEqual(image_path.read_bytes(), image_bytes)


if __name__ == "__main__":
    unittest.main()
