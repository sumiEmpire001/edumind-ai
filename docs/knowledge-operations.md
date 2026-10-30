# Knowledge operations

1. Run the additive Alembic migration once before deploying the API. Back up real databases;
   do not reset tables or volumes. The free Render test DB expires 29 November 2026.
2. Configure private objects using either:
   - BLOB_STORE_ID and BLOB_READ_WRITE_TOKEN, or
   - STORAGE_BUCKET, STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, STORAGE_REGION and optionally
     an HTTPS STORAGE_ENDPOINT for S3-compatible storage.
   The API fails clearly and disables upload in the UI until credentials are configured.
3. Deploy the separate worker with the same backend image and start command
   `python -m app.knowledge.worker`. Give it the API database/storage/Gemini environment.
   Resource-limit it; document parsing must not share the public API's process.
4. Create an administrator through the existing private bootstrap command. Never add an
   unauthenticated admin signup endpoint. Review contributor applications in Knowledge library.
5. Test upload -> pending -> original/text preview -> approve -> queued -> succeeded.
   Confirm the worker generated 768-dimensional embeddings with the configured model.
   Reject another document and confirm no job/vector was created. Try as a student/contributor
   to prove admin endpoints are forbidden. Test duplicates and a malformed file.
6. Enable RAG_ENABLED=true only after those gates pass. Ask a question answered by the approved
   material. Verify references and page/section locations; ask an unrelated question and verify
   no invented school-specific details. Disable/remove a source and repeat the question.
7. Re-index through the administrator control after a recoverable processing failure. It
   deactivates the old version and resets the job. Changing embedding models requires a
   deliberate re-indexing migration; mixed models are excluded, never compared.

Failed extraction/embedding uses generic error codes; credentials and document contents are
not logged. Worker leases expire after ten minutes and allow crash recovery. Automatic SDK
retries are bounded. After three worker claims, investigate/requeue rather than looping forever.
Objects orphaned by a database/storage commit failure require private-bucket reconciliation.
Original private objects and past source records remain after removal from retrieval.

Vercel frontend configuration: VITE_API_BASE_URL=/ and an API rewrite before SPA fallback.
Render CORS_ORIGINS must name the exact frontend origin. Keep secure HttpOnly cookies and
CSRF origin checks enabled. Vercel protection currently prevents anonymous site visits;
public access requires separate explicit approval after automatic review rejection.
