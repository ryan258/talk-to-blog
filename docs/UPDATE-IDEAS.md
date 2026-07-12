# UPDATE-IDEAS — Active backlog

Completed work has moved to [changelog.md](../changelog.md). This document now tracks only
open decisions and deliberate non-goals.

## Completed on 2026-07-11

- [x] Output styles: blog, notes, summary, actions, flashcards, and ELI5.
- [x] Anki-ready flashcard CSV export.
- [x] Generated title, description, and tags.
- [x] Lazy multi-chunk coherence context.
- [x] YouTube, stdin, format inference, and batch input.
- [x] Retry/resume, progress, usage reporting, and dry runs.
- [x] OpenAI-compatible local endpoints and custom prompt files.
- [x] Flexible YAML frontmatter and speaker-aware conversions.
- [x] Modern packaging, version reporting, CI, and generated-artifact cleanup.

## Open items

- [ ] Measure the lazy coherence context on representative long talks. Add the optional
  outline-first second pass only if the results show it is needed; it adds an API call and cost.
- [ ] Publish version 0.2.0 to PyPI and verify `pipx install talk-to-blog`. This requires
  release authority and PyPI credentials.

## Deliberate non-goals

- [ ] Audio transcription remains YAGNI. If demand establishes a need, document a
  `whisper.cpp` workflow before considering built-in transcription.
- [ ] No direct publishing integrations, parallel conversion, plugin system, RAG knowledge base,
  or non-stdlib runtime dependencies.
