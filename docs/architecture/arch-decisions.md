# Architectural Decisions & ETC

- **Functional Purity (ETC):** Deep reliance on pure functions for text transformation maximizes testability and ensures side-effects do not propagate.
- **Minimalist Tooling (ETC):** Using purely standard library modules instead of heavy NLP libraries yields rapid refactor cycles and avoids dependency rot.
- **Subsystem Isolation:** Chunking, frontmatter generation, transcript text-cleaning, and subtitle parsing are isolated into distinct single-purpose functions.
- **Graceful Fallbacks:** Guaranteed system defaults (author, title, date) to prevent input validation failures from stopping processing.
- **Extensible Parser Switch:** The unified `convert_transcript_to_blog` cleanly delegates to distinct format parsers, making adding formats (e.g., JSON) trivial.
