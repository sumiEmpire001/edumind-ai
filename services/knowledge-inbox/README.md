# Personal administrator knowledge inbox

This separate service watches a folder on your computer and submits academic files to
EduMind over HTTPS. It never approves documents. The server independently validates
uploads and creates only PENDING submissions. Rejected/pending files never enter RAG.

## Windows setup

1. Install Python 3.12 or newer from python.org. Download this directory from the repository.
2. Sign in to EduMind as an administrator and open Knowledge library -> Personal knowledge
   inbox. Create an expiring submission-only credential. Copy it privately; it is shown once.
3. Open PowerShell in this directory and run `./Start-Inbox.ps1`. Enter the credential at
   the masked prompt. Use the standard signed-script execution policy required by your
   computer; do not disable your organization's policy. Alternatively use the Python CLI
   below with a token supplied by your OS secret manager.
4. Place PDF, DOCX, TXT, CSV or PPTX files up to 3 MB in `EduMind-Knowledge-Inbox/incoming`.
5. In the online admin dashboard, preview and approve or reject each pending document.
   Approved files still wait for successful worker processing before becoming searchable.

The PowerShell wrapper clears its token environment variable when it exits and never
writes the token into a file or command history. Credentials expire after at most 90 days
and can be revoked in EduMind. Use different credentials for different computers. An
inactive/non-admin owner invalidates their service credentials. Never use your account
password, access JWT or Gemini key as an inbox credential.

## Portable CLI

Use Python's standard library; no pip packages are required:

    python inbox.py --backend https://edumind-test-api.onrender.com --folder ./EduMind-Knowledge-Inbox

Supply `EDUMIND_INBOX_TOKEN` through a private environment/OS-secret-manager configuration.
Do not paste tokens into shared terminals or commit them. `--once` scans once; normal
operation polls every two seconds. Files must remain unchanged for six seconds before
processing. `--retry-failed` explicitly requeues failed journal entries after a fix.

    incoming/      Files being copied or waiting for validation
    processing/    Stable files awaiting upload/retry
    completed/     Successfully submitted or already-known documents
    failed/        Invalid files or exhausted/permanent failures
    journal.sqlite3    Durable content hashes, paths, retry state; no credentials

Keep all folders on the same local filesystem for atomic renames. Close document editors
before copying. Stability checks, before/after stat checks and a hash recheck reduce partial
copy races; a writer pausing longer than the stability window can still cause a validation
failure. Failed files are preserved for review. The journal prevents repeated submissions
across restarts; backend content hashes provide a second independent duplicate boundary.

Do not rename/delete journal files while the service runs. Only one process may own a
folder. The service retries network failures, HTTP 429 and transient 5xx failures with
bounded exponential backoff. Authentication failures stop it with files intact so you can
renew/revoke credentials. HTTP redirects are refused, avoiding credential forwarding.
A local computer/service outage does not affect the cloud API. This service cannot run
inside the Vercel frontend, and a phone does not provide access to your Windows folders.

Run tests: `python -m unittest -v test_inbox`. CI runs the suite on Linux and Windows.
