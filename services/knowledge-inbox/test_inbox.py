import hashlib
import tempfile
import unittest
from pathlib import Path

from inbox import AuthenticationFailure, Inbox, NoRedirect, Transport


class FakeTransport:
    def __init__(self, statuses=None):
        self.statuses = iter(statuses or [201])
        self.calls = []

    def submit(self, filename, data, mime):
        self.calls.append((filename, data, mime))
        return next(self.statuses), "submission-id"


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.time = 1000
        self.transport = FakeTransport()
        self.inbox = Inbox(self.root, self.transport, stable_seconds=2, clock=lambda: self.time)

    def tearDown(self):
        self.inbox.close()
        self.temp.cleanup()

    def file(self, text=b"A physics lesson", name="lesson.txt"):
        path = self.root / "incoming" / name
        path.write_bytes(text)
        return path

    def stage(self):
        self.inbox.scan_once()
        self.time += 3

    def test_waits_for_stable_copy(self):
        path = self.file()
        self.assertEqual(self.inbox.scan_once(), 0)
        self.time += 1
        path.write_bytes(b"Still copying the physics lesson")
        self.assertEqual(self.inbox.scan_once(), 0)
        self.time += 3
        self.assertEqual(self.inbox.scan_once(), 1)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(len(list((self.root / "completed").iterdir())), 1)

    def test_duplicates_never_submit_twice(self):
        self.file()
        self.stage()
        self.inbox.scan_once()
        self.file(name="duplicate.txt")
        self.stage()
        self.inbox.scan_once()
        self.assertEqual(len(self.transport.calls), 1)

    def test_backend_duplicate_is_completed(self):
        self.inbox.transport = FakeTransport([409])
        self.file()
        self.stage()
        self.assertEqual(self.inbox.scan_once(), 1)

    def test_retry_survives_restart(self):
        transport = FakeTransport([503, 201])
        self.inbox.transport = transport
        self.file()
        self.stage()
        self.inbox.scan_once()
        self.assertEqual(len(transport.calls), 1)
        self.inbox.close()
        self.inbox = Inbox(self.root, transport, clock=lambda: self.time)
        self.inbox.scan_once()
        self.assertEqual(len(transport.calls), 1)
        self.time += 3
        self.assertEqual(self.inbox.scan_once(), 1)

    def test_auth_failure_preserves_pending_file(self):
        self.inbox.transport = FakeTransport([401])
        self.file()
        self.stage()
        with self.assertRaises(AuthenticationFailure):
            self.inbox.scan_once()
        self.assertEqual(self.inbox.db.execute("SELECT status FROM files").fetchone()[0], "pending")
        self.assertEqual(len(list((self.root / "processing").iterdir())), 1)

    def test_permanent_rejection_preserves_original(self):
        self.inbox.transport = FakeTransport([422, 201])
        self.file()
        self.stage()
        self.inbox.scan_once()
        self.assertEqual(len(list((self.root / "failed").iterdir())), 1)
        self.inbox.requeue_failed()
        self.assertEqual(self.inbox.scan_once(), 1)

    def test_invalid_file_moves_to_failed(self):
        self.file(b"not a PDF", "fake.pdf")
        self.stage()
        self.inbox.scan_once()
        self.assertEqual(len(self.transport.calls), 0)
        self.assertEqual(len(list((self.root / "failed").iterdir())), 1)

    def test_staged_journal_recovers_before_rename(self):
        path = self.file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        destination = self.root / "processing" / (digest[:12] + "-lesson.txt")
        self.inbox.db.execute(
            "INSERT INTO files(digest,original_name,path,status) VALUES(?,?,?,?)",
            (digest, "lesson.txt", str(destination), "staged"),
        )
        self.inbox.db.commit()
        self.assertEqual(self.inbox.scan_once(), 1)

    def test_move_before_commit_recovers_without_resubmission(self):
        path = self.file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target = self.root / "processing" / "lesson.txt"
        path.replace(self.root / "completed" / "lesson.txt")
        self.inbox.db.execute(
            "INSERT INTO files(digest,original_name,path,status) VALUES(?,?,?,?)",
            (digest, "lesson.txt", str(target), "pending"),
        )
        self.inbox.db.commit()
        self.inbox.scan_once()
        self.assertEqual(len(self.transport.calls), 0)
        self.assertEqual(
            self.inbox.db.execute("SELECT status FROM files").fetchone()[0], "completed"
        )

    def test_token_never_stored_in_journal(self):
        self.file()
        self.stage()
        self.inbox.scan_once()
        data = self.inbox.db.iterdump()
        self.assertNotIn("emi_", "\n".join(data))

    def test_http_and_redirect_credentials_rejected(self):
        for origin in [
            "http://example.com",
            "https://a.example/path",
            "https://user:pass@a.example",
            "https://a.example?token=secret",
        ]:
            with self.assertRaises(ValueError):
                Transport(origin, "emi_test")
        self.assertIsNone(
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example")
        )


if __name__ == "__main__":
    unittest.main()
