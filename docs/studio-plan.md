# EduMind Studio: chat, attachments and long documents

Turn EduMind into an academic assistant that can work with a learner's materials and
produce editable documents and downloadable PDFs, including substantial 30–45-page reports.

## User experience

1. Ask a question in study chat; optionally attach PNG/JPEG images or UTF-8 text notes.
2. Ask follow-ups, copy an answer, or download an answer/the full conversation as PDF.
3. Open Document Studio, describe the report, choose a target length and edit its outline.
4. Generate one section or draft the outline in sequence, with saved progress and a stop
   control between sections. Resume the current request after an interrupted connection.
5. Edit the text, regenerate selected sections and export a typeset PDF with a title page,
   contents, section headings and numbered pages. Show actual exported pages and word count.

Page targets guide the writing budget; they are not proof of length. Never pad with blank
pages or claim an unfinished draft is complete. Generated academic statements and references
need review. Never invent a bibliography, institutional facts or experimental results.

## This implementation

- Owner-checked durable drafts, optimistic revisions and generation recovery using the
  existing idempotent chat engine. Section generation has bounded provider calls; no new
  paid worker is required for text drafting or PDF exports.
- Private, owner/conversation-scoped attachments with bounded byte and pixel limits,
  allowlisted file types, ownership checks on every use, and image-understanding parts
  passed directly to Gemini. No browser key, public file URL, or global knowledge indexing.
- Attachments require the already-planned private store credential. A visible capability
  state disables uploads when it is absent. Uploaded notes remain personal chat context;
  they do not bypass contributor review or become approved learning references.
- PDF generation uses a server-side renderer without fetching remote HTML, CSS or images.
  Markdown tables/code are supported; complex LaTeX is preserved as source notation.
- Image generation is an optional later provider integration, disabled in this release.
  Current image understanding and future image generation are different capabilities.
  This milestone adds no paid hosting and does not authorize an image-generation purchase.

## Acceptance checks

Verify actual PDF bytes/page count, Unicode/common academic symbols, 30–45-page synthetic
layout, draft persistence/revisions, lost-response recovery, concurrency/owner isolation,
provider failure, attachment spoofing/size/pixel limits and private storage failures.
Test the complete draft/edit/export and attachment chat workflows on desktop/mobile.
Hosted upload/vision checks remain conditional on private storage configuration; live image
generation must never be advertised while disabled.
