# Long answers and the academic starter collection

## Answer handling

Study Chat requests up to 16,384 output tokens instead of 4,096. The provider accepts
up to 60,000 characters (formerly 12,000); token limits do not guarantee a word count.
The tutor follows requested depth and structures reports with headings and substantive
paragraphs, without fabricated data or references. Native MAX_TOKENS responses retain
the available text and a continuation notice. Safety blocks and empty responses still
fail. Continue answer prepares a follow-up in the composer for the student to send.
Sources are appended without silently truncating prose. Long answers remain in the
80,000-character default conversation budget. Long answers imported into Studio split
into editable sections of at most 28,000 characters. PDF exports use existing formatting.

Provider timeout defaults to 50 seconds and total generation timeout to 55 seconds;
these remain bounded and can be overridden by deployment configuration. Larger
responses consume more provider quota. This is not unlimited generation or streaming.
A network timeout still produces a retryable failure, not a saved partial response.

## Licensed starter collection, v1

`backend/app/knowledge/corpus/` contains selected text, not complete textbooks:

- Suzan Last, *Technical Writing Essentials*, University of Victoria / BCcampus,
  2019, CC BY 4.0: research terminology, defining research scope, laboratory reports,
  and long reports / feasibility studies. Long reports also credits David Murrey's
  openly licensed source chapter. Navigation and link markers were removed;
  third-party images and linked supplementary works are excluded.
- David Diez, Mine Çetinkaya-Rundel, Christopher Barr, *OpenIntro Statistics*,
  CC BY-SA 3.0: selected prose on data, sampling, observational studies, and
  experiments. This derivative text is CC BY-SA 3.0; it is not endorsed by OpenIntro.
  Equations, exercises, figures, and typesetting were omitted. The source commit
  and chapter path are recorded in statistics.json. The full upstream licence is
  retained beside that file. This content licence applies to the derivative
  educational text, not unrelated application code.

Original chapter URLs, authors, licences, transformations and source sections are
stored with each record. Attribution accompanies indexed passages and chat reference
footers. These are general academic resources, not LAUTECH-specific regulations.
No private student reports, publisher-restricted books, or teacher-only materials
are included. Content is evidence, never system instructions.

## Import and removal

Set `KNOWLEDGE_STARTER_ENABLED=true` on a deployment with the text worker enabled.
The worker installs the operator-authorized collection once, stores the original
text privately, and records approved submissions, active lexical-search chunks,
successful processing jobs and audit events. Stable IDs make repeated starts safe.
Existing records, including removed documents, are skipped. Ordinary contributor
submissions still require admin approval. No schema migration is needed.

Import logs report each source and chunk count plus `knowledge_starter_complete`.
The import can also be called directly using `app.knowledge.starter.install` with
an authenticated operational engine and store. Import failures are logged without
blocking normal processing; retry by restarting after correcting the cause.

This builds retrieval knowledge, not a new model or fine-tuning dataset. Training
example and evaluation counts are deliberately unchanged. Tests check six retrieval
questions and a no-match case; they are smoke tests, not an independent benchmark
of answer quality, reasoning, or university-wide coverage.
