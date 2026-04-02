# Execution Context & Pragmatic Paranoia

- **Flow Control:** 
  1. `main()` parses strictly typed CLI args, validates `--chunk-size`, and resolves the current-date fallback before calling the pure layer.
  2. Input Read -> File content extraction wrapped in try/except block.
  3. Core Planning -> `prepare_conversion_request()` parses, cleans, resolves title/author defaults, and chunks transcript text without side effects.
  4. External Call -> CLI sends each prepared prompt to OpenRouter and validates HTTP status plus response shape.
  5. Output Compose -> `convert_transcript_to_blog()` assembles the final Markdown document from AI body sections.
  6. Output Write -> I/O execution wrapped with final stderr/exit handling.
- **Error Trapping:** CLI catches `OSError`, HTTP failures, JSON decode failures, and malformed API payloads before printing a sanitized message and exiting non-zero.
- **Defensive Regex:** Speaker-label and filler removal patterns are anchored to transcript boundaries to avoid stripping ordinary prose.
- **Defensive Parsing Paranoia:** Invalid SRT blocks are skipped unless they include a well-formed timestamp line, preventing malformed identifiers and body text from leaking into parsed output.
