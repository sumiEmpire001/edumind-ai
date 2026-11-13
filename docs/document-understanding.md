# Document extraction and grounded answers

## Findings and changes

Previously the contributor PDF parser read only embedded text. Scans without a text
layer failed. Natural questions matching a short document topic could bypass the
language model and return excerpts verbatim. The optional vector retrieval adapter
was separate from the default text-only index.

Approved PDFs now use local Poppler + Tesseract English OCR for image-bearing pages
with fewer than 80 native-text characters. Native text pages are preserved. OCR page
locations include `(OCR)` and metadata records processed page numbers. The original
upload is kept. Indexed text can be inspected with Preview document text. Before
approval, preview reads native text only; review the original scan before approving.

OCR is bounded to 40 candidate pages, 2000-pixel rendering, 20 seconds per process,
180 seconds per document, one Tesseract thread, and the existing isolated worker
memory ceiling. Low mean OCR confidence or an unreadable image page fails the entire
indexing job instead of silently publishing partial text. Admin sees an actionable
failure message and may upload a clearer version or retry after fixing the cause.

Ordinary Study Chat questions now retrieve approved, active, current-version document
passages and pass them to the configured tutor, with the original question. The model
is asked to explain the answer, distinguish deductions, cite supplied page sources,
and state missing or uncertain evidence. Sources are rechecked before saving the
answer. The explicit contributor/admin `/knowledge` command remains an excerpt search.
Student Knowledge API access remains restricted.

## Deployment and verification

Backend Docker image includes Poppler and Tesseract English data. No new Python
packages, paid OCR provider, or schema migration are required. CI installs the same
OCR utilities and exercises real image-PDF transcription, mixed page numbering,
approval gating, indexed preview, and failure exclusion. Existing natural-question
tests now assert that evidence reaches the tutor rather than bypassing it.

After deploying, re-index previously failed approved scans in the admin Knowledge
library, then inspect the text preview before relying on answers. Existing successful
text indexes do not require re-indexing.

## Limits

This is retrieval-augmented generation, not training an independent model. The default
retrieval still uses keywords (optional embedding retrieval exists separately); it can
miss paraphrases, broad whole-document questions, or follow-ups without topic words.
Model instructions improve answer construction but cannot prove comprehension or
factual accuracy. A live model evaluation against reviewed questions remains necessary.

OCR is aimed at clear printed English. Handwriting, equations, tables, rotated or blurry
photos, and pages mixing substantial native text with scanned content may be incomplete
or incorrect. Confidence scores are a rejection heuristic, not an accuracy guarantee.
The system does not interpret diagrams. Complex scans need manual transcription/review;
there is no handwriting recognition guarantee or automatic equation reconstruction.
Scanned PDFs attached privately to Study Chat still follow the separate attachment
rules; this change is for contributed/approved Knowledge library PDFs.

## Handwriting vision workflow

For approved handwritten PDFs, admins can expand **Handwritten PDF?** and choose
**Read handwriting**. This explicitly sends each rendered page image to the configured
Gemini model using the existing API key and quota. Local printed-text OCR remains the
default. The handwriting path supports at most 10 PDF pages per job, renders one page
at a time at a maximum dimension of 2000 pixels, and uses bounded per-request timeouts.
No billing settings or model weights are changed.

Vision output is a literal transcription, not a summary or solution. The prompt preserves
reading order and asks for `[unclear]` instead of guesses. JSON shape, text length and
completion status are validated. Quota, malformed response and truncation failures do
not publish a partial index. The document is excluded from search when the job is queued.

All successful vision transcriptions are saved as inactive drafts. **Review transcription**
shows each page and provides the original PDF download. An admin must compare the text
with the original, correct uncertain words/numbers/symbols, and approve it. Approval rejects
unresolved `[unclear]` markers, missing/reordered pages and stale versions, then creates a
new searchable chunk version and records who reviewed it. A removed or reprocessing document
cannot be published from an old draft. Draft text is not returned to students or indexed
for answers. Contributors cannot request or approve handwriting jobs.

The original printed-OCR limitations above still apply to that default path. Vision helps
with handwriting but can also misread it, including confident mistakes. Human review is
mandatory; no handwriting accuracy percentage has been measured. Automated tests exercise
image rendering, protocol validation, review access controls, version safety and search
exclusion using deterministic provider responses. They do not constitute a live-model
handwriting accuracy benchmark. Evaluate actual handwriting samples before relying on
transcriptions for equations or numerical results.

## Automatic scan processing and removal

Approval now chooses the extraction path automatically. Native-text PDFs retain the
local parser. Scans detected by local OCR (up to 10 total PDF pages) go through Gemini
vision when configured; unreadable local OCR also falls back to vision. The optional
advanced retry remains available, but users do not have to identify handwriting.
Vision drafts still require transcription review before search publication.

On worker startup, previously failed approved PDFs with recoverable text/OCR errors
receive one automatic vision retry. A persistent marker prevents repeated retries
across restarts, and removed documents are never recovered. Quota and provider failures
remain explicit failures requiring investigation rather than an unlimited retry loop.

Remove from retrieval is available even for failed documents. Removal excludes material
from future retrieval, prevents automatic recovery, and prevents previous source-backed
answers from being reused as model context after their source is removed or superseded.
Saved historical answers and original files are retained; this operation is not permanent
file deletion. The administration screen distinguishes removed documents from failures.
