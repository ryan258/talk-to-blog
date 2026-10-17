# Changelog

All notable user-facing changes are recorded here.

## [Unreleased]

### Changed

- The `actions` style now extracts decisions, explicit commitments, open questions, and suggestions
  that were never adopted, each with a source location (sparse `[HH:MM:SS]` markers from SRT/VTT,
  otherwise the chunk label).

## [0.2.0] - 2026-07-11

### Added

- Learning artifact styles: blog posts, study notes, summaries, action plans, flashcards, and
  plain-language explanations.
- Anki-ready CSV export for flashcards.
- Automatic title, description, and tag generation when no title is supplied.
- YouTube caption input through optional `yt-dlp`, stdin input, subtitle format inference, and
  sequential directory batch conversion with a per-file summary.
- OpenAI-compatible endpoint overrides for local services, plus custom prompt-file overrides.
- Repeatable `--meta` frontmatter fields and `--keep-speakers` for interviews and panels.
- `--version`, a Python 3.8–3.12 test workflow, and a YouTube happy-path guide.
- A local loopback web UI for pasted transcripts and YouTube links.

### Changed

- Later transcript chunks receive all previously generated headings and recent context to improve
  coherence without adding an outline API call.
- Speaker-aware conversions preserve conversational attribution; common article-led prose labels
  are no longer mistaken for speaker names.
- Package configuration now uses `pyproject.toml` exclusively.

### Fixed

- Retry transient API failures and resume interrupted multi-chunk conversions from partial state.
- Report per-chunk progress, aggregate token usage, and dry-run prompt plans.
- Remove tracked generated `*.egg-info` metadata and the obsolete completion-state file.
