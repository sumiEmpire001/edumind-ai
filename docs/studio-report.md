# Studio release evidence and remaining gates

EduMind Studio implements the [requested idea](studio-plan.md): personal chat materials,
editable long reports and downloadable PDFs. Implementation and follow-up fixes are in
PRs #8–#11. No paid service or image-generation provider was provisioned.

## Delivered behavior

- Owner-scoped saved reports, editable outlines, 10–45-page targets, sequential section
  drafting, stop between sections, interrupted-request recovery, manual editing,
  regeneration and selected-section expansion.
- Server-rendered PDF exports for reports, answers and conversations. Reports have a
  cover, contents and page numbers. Actual page/word counts are shown; targets guide
  drafting and no blank padding is added to meet them.
- Private PNG/JPEG and UTF-8 TXT attachment support with authenticated image previews,
  unused-upload recovery, normalized images, owner/conversation checks and byte/pixel/
  quota/concurrency limits. Attachments stay outside the reviewed knowledge index.
- Gemini inline image understanding when private storage is configured. Image generation
  is explicitly disabled. Live uploads remain visibly unavailable without the store credential.
- Additive migration 0006_studio. Report backing histories are isolated from regular
  conversations. Durable reservations and optimistic revisions protect generation and edits.

Generation is bounded: at most 900 requested words per section, about 500 per expansion,
4096 output tokens, 12,000 saved answer characters and a 60-second overall production
request deadline. Gemini 2.5 Flash reasoning is bounded at 128 tokens. A provider attempt
can use the full request deadline. Incomplete outputs are rejected. Longer reports build
up through saved sections and expansions while the browser remains open.

## Automated verification

Final implementation run 41146020236 passed every GitHub job. The suite comprises
165 PostgreSQL backend tests without skips, 50 frontend tests, 30 desktop Chromium/mobile
WebKit browser cases, dependency audits and 11 inbox tests on each of Linux and Windows.
Earlier complete Studio runs 41142762721 and 41144322302 also passed.

Coverage includes the additive migration, owner isolation, revision conflicts, replay and
recovery after interruption, deletion during generation, provider failures, attachment
validation/quotas, concurrent image limits and parsed PDF bytes/page counts. Browser
checks cover drafting, expansion, editing, reload, export and attachment chat. PDF cover,
contents and content pages were rendered and visually inspected, including Unicode,
tables and code. Complex LaTeX is retained as source notation.

## Hosted evidence

The frontend is READY as Vercel dpl_38PqawLKe8e2SroV9mPmWQcwxUfY on release
35bd6f638912a82b07400f0823f0c5e4b0191b54. Its source is unchanged by the later API fixes.
The latest API release is f304e61d1f73e600646933b81f5699ba2bf49ea7, Render deployment
dep-dbiioe8473hc73d7ulb0 (live).

Public-frontend-origin checks passed registration/login, twelve manual section saves,
persistence, and export of 11,400 words as a real 31-page PDF. Every page contained text,
and the reported count matched the parsed PDF. This was a marked synthetic layout fixture,
not an AI-generated academic report. A separate short live Gemini question succeeded.
Test drafts/conversations were soft-removed and the sessions logged out. Capabilities
correctly reported uploads and image generation unavailable, and a 60-second request limit.

Live report checks exposed provider timeouts and then MAX_TOKENS; the deadline, reasoning
and output budgets above address those findings. The final live check after the output
budget change was blocked by Gemini HTTP 429 (quota/rate limit). No billing was enabled
and no further model calls were made after that result. Long-section drafting, replay
and generated-section export remain a hosted verification gate until quota is available.
Do not claim a successful full live
30–45-page AI report based on the synthetic renderer/export tests or one generated section.

## Remaining activation gates

- Live private uploads and hosted vision require the existing private store credential,
  which remains unconfigured. Automated storage/provider tests do not replace this gate.
- Image generation is not enabled or purchased.
- Users must review academic claims, calculations and references, then expand/edit until
  the actual exported length and content meet their requirements.
- The broader [readiness gates](final-readiness.md) remain, including the separate reviewed-
  knowledge worker, administrator setup, hosted storage/RAG, backup restore, and the user's
  actual Windows inbox. This extension does not complete the whole original roadmap.
