"""Windows-compatible, submission-only EduMind knowledge inbox. Standard library only."""

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MIMES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
MAX_BYTES = 3 * 1024 * 1024
log = logging.getLogger("edumind.inbox")


class AuthenticationFailure(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to another location.


class Transport:
    def __init__(self, base_url, token, allow_local_http=False):
        url = urllib.parse.urlsplit(base_url)
        local = (
            url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"} and allow_local_http
        )
        if (
            (url.scheme != "https" and not local)
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Use an HTTPS backend origin, without a path or credentials")
        token = token.strip()
        if (
            not token.startswith("emi_")
            or len(token) > 128
            or not token.isascii()
            or any(c.isspace() for c in token)
        ):
            raise ValueError("A scoped inbox credential is required")
        self.base, self.token = base_url.rstrip("/"), token
        self.opener = urllib.request.build_opener(NoRedirect())

    def submit(self, filename, data, mime):
        query = urllib.parse.urlencode({"filename": filename, "title": Path(filename).stem[:200]})
        request = urllib.request.Request(
            self.base + "/api/v1/inbox/submissions?" + query,
            data=data,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": mime},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=40) as response:
                if response.status != 201:
                    return response.status, None
                body = json.loads(response.read(65536))
                if body.get("status") != "pending":
                    raise ValueError("Backend did not preserve administrator review")
                return 201, body.get("id")
        except urllib.error.HTTPError as exc:
            # Response bodies may contain private/internal details; never log or persist them.
            return exc.code, None


def validate(path, data):
    ext = path.suffix.lower()
    if ext not in MIMES or not data or len(data) > MAX_BYTES:
        raise ValueError("unsupported_or_oversized_file")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf")
    if ext in {".txt", ".csv"}:
        if "\x00" in data.decode("utf-8-sig"):
            raise ValueError("invalid_text")
    if ext in {".docx", ".pptx"}:
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1500 or sum(e.file_size for e in entries) > 20 * MAX_BYTES:
                raise ValueError("archive_limits")
            expected = "word/document.xml" if ext == ".docx" else "ppt/presentation.xml"
            if (
                expected not in archive.namelist()
                or "[Content_Types].xml" not in archive.namelist()
            ):
                raise ValueError("invalid_office_file")
    return MIMES[ext]


class Inbox:
    def __init__(self, root, transport, stable_seconds=6, clock=time.time):
        self.root, self.transport, self.clock = Path(root), transport, clock
        self.stable_seconds = max(2, stable_seconds)
        for folder in ["incoming", "processing", "completed", "failed"]:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "journal.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS files (
            digest TEXT PRIMARY KEY, original_name TEXT NOT NULL, path TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            next_retry REAL NOT NULL DEFAULT 0, submission_id TEXT, error_code TEXT)""")
        self.db.commit()
        self.observed = {}

    def close(self):
        self.db.close()

    def requeue_failed(self):
        self.db.execute(
            "UPDATE files SET status='pending',attempts=0,next_retry=0,error_code=NULL "
            "WHERE status='failed'"
        )
        self.db.commit()

    def move(self, path, folder):
        destination = self.root / folder / path.name
        if destination.exists():
            destination = destination.with_name(str(time.time_ns()) + "-" + destination.name)
        path.replace(destination)
        return destination

    def discover(self):
        for path in sorted((self.root / "incoming").iterdir()):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.name.startswith(".")
                or path.suffix.lower() not in MIMES
            ):
                continue
            try:
                stat = path.stat()
                fingerprint = (stat.st_size, stat.st_mtime_ns)
                previous = self.observed.get(path)
                if not previous or previous[0] != fingerprint:
                    self.observed[path] = (fingerprint, self.clock())
                    continue
                if self.clock() - previous[1] < self.stable_seconds:
                    continue
                if stat.st_size > MAX_BYTES:
                    self.move(path, "failed")
                    log.warning("file_rejected category=size_limit")
                    continue
                with path.open("rb") as source:
                    data = source.read(MAX_BYTES + 1)
                after = path.stat()
                if fingerprint != (after.st_size, after.st_mtime_ns):
                    self.observed.pop(path, None)
                    continue
                digest = hashlib.sha256(data).hexdigest()
                existing = self.db.execute(
                    "SELECT status FROM files WHERE digest=?", (digest,)
                ).fetchone()
                if existing:
                    self.move(path, "completed" if existing[0] == "completed" else "failed")
                    continue
                try:
                    validate(path, data)
                except (ValueError, UnicodeError, zipfile.BadZipFile):
                    self.move(path, "failed")
                    log.warning("file_rejected category=validation")
                    continue
                # Journal first, then atomically rename. Recovery checks both old/new paths.
                destination = self.root / "processing" / (digest[:12] + "-" + path.name)
                self.db.execute(
                    "INSERT INTO files(digest,original_name,path,status) VALUES (?,?,?,?)",
                    (digest, path.name, str(destination), "staged"),
                )
                self.db.commit()
                path.replace(destination)
                self.db.execute("UPDATE files SET status='pending' WHERE digest=?", (digest,))
                self.db.commit()
                self.observed.pop(path, None)
            except OSError:
                log.info("file_busy_retry")

    def recover_staged(self):
        for digest, name, target in self.db.execute(
            "SELECT digest,original_name,path FROM files WHERE status='staged'"
        ).fetchall():
            path = Path(target)
            if not path.exists():
                original = self.root / "incoming" / name
                if not original.exists():
                    self.db.execute(
                        "UPDATE files SET status='failed',error_code='missing_file' WHERE digest=?",
                        (digest,),
                    )
                    continue
                original.replace(path)
            self.db.execute("UPDATE files SET status='pending' WHERE digest=?", (digest,))
        self.db.commit()

    def scan_once(self):
        self.recover_staged()
        self.discover()
        rows = self.db.execute(
            "SELECT digest,original_name,path,attempts FROM files "
            "WHERE status='pending' AND next_retry<=?",
            (self.clock(),),
        ).fetchall()
        processed = 0
        for digest, name, raw_path, attempts in rows:
            path = Path(raw_path)
            if not path.exists():
                completed = self.root / "completed" / path.name
                if (
                    completed.exists()
                    and hashlib.sha256(completed.read_bytes()).hexdigest() == digest
                ):
                    self.db.execute(
                        "UPDATE files SET status='completed',path=? WHERE digest=?",
                        (str(completed), digest),
                    )
                    self.db.commit()
                    continue
            status, submission_id = 0, None
            try:
                with path.open("rb") as source:
                    data = source.read(MAX_BYTES + 1)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("content_changed")
                mime = validate(Path(name), data)
                status, submission_id = self.transport.submit(name, data, mime)
            except (OSError, TimeoutError, urllib.error.URLError):
                status = 0
            except (ValueError, UnicodeError, zipfile.BadZipFile):
                status = 422
            if status in {401, 403}:
                log.error("inbox_authentication_failed; replace_or_renew_scoped_credential")
                raise AuthenticationFailure("Inbox authorization failed")
            if status in {201, 409}:
                destination = self.move(path, "completed")
                self.db.execute(
                    "UPDATE files SET status='completed',path=?,submission_id=?,error_code=NULL "
                    "WHERE digest=?",
                    (str(destination), submission_id, digest),
                )
                processed += 1
                log.info("submission_accepted review=pending_or_existing")
            elif (status == 0 or status in {408, 425, 429} or status >= 500) and attempts < 7:
                delay = min(300, 2 ** (attempts + 1))
                self.db.execute(
                    "UPDATE files SET attempts=attempts+1,next_retry=?,error_code=? WHERE digest=?",
                    (self.clock() + delay, "retry_" + str(status), digest),
                )
                log.warning("submission_retry category=%s delay=%s", status, delay)
            else:
                destination = self.move(path, "failed") if path.exists() else path
                self.db.execute(
                    "UPDATE files SET status='failed',path=?,error_code=? WHERE digest=?",
                    (str(destination), "http_" + str(status), digest),
                )
                log.warning("submission_failed category=%s", status)
            self.db.commit()
        return processed


def lock_instance(root):
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    handle = open(path / "service.lock", "a+b")
    handle.write(b"0")
    handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Another inbox service is running") from None
    return handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", default="EduMind-Knowledge-Inbox")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("EDUMIND_INBOX_TOKEN", "")
    transport = Transport(args.backend, token)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    instance_lock = lock_instance(args.folder)
    inbox = Inbox(args.folder, transport)
    if args.retry_failed:
        inbox.requeue_failed()
    try:
        while True:
            inbox.scan_once()
            if args.once:
                break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    except AuthenticationFailure:
        raise SystemExit(2) from None
    finally:
        inbox.close()
        instance_lock.close()


if __name__ == "__main__":
    main()
