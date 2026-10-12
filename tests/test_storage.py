import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reload_storage():
    import src.storage
    return importlib.reload(src.storage)


class SeenFilePathTest(unittest.TestCase):
    def tearDown(self):
        # 다른 테스트에 영향이 없도록 기본값으로 되돌린다.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEEN_FILE", None)
            _reload_storage()

    def test_default_path_is_repo_file(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEEN_FILE", None)
            storage = _reload_storage()
        self.assertEqual(storage.SEEN_FILE, "seen_posts.txt")

    def test_empty_env_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"SEEN_FILE": "   "}):
            storage = _reload_storage()
        self.assertEqual(storage.SEEN_FILE, "seen_posts.txt")

    def test_env_overrides_path_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state", "seen_posts.txt")
            os.makedirs(os.path.dirname(path))
            with mock.patch.dict(os.environ, {"SEEN_FILE": path}):
                storage = _reload_storage()
                self.assertEqual(storage.SEEN_FILE, path)
                self.assertEqual(storage.load_seen(), [])
                storage.save_seen(["a", "b"])
                self.assertEqual(storage.load_seen(), ["a", "b"])
            self.assertTrue(os.path.exists(path))

    def test_save_keeps_only_recent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seen_posts.txt")
            with mock.patch.dict(os.environ, {"SEEN_FILE": path}):
                storage = _reload_storage()
                storage.save_seen([str(i) for i in range(storage.MAX_RECORDS + 5)])
                loaded = storage.load_seen()
        self.assertEqual(len(loaded), storage.MAX_RECORDS)
        self.assertEqual(loaded[0], "5")


if __name__ == "__main__":
    unittest.main()
