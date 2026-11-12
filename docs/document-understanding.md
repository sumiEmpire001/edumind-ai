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
