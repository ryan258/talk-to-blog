# UPDATE-IDEAS — Making talk-to-blog exceptional for self-learning professionals

Status: implemented in the working tree, 2026-07-11. PyPI publication remains an external release task.
Source: full code review of `talk_to_blog/converter.py`, `talk_to_blog/cli.py`, tests, and README.

## Where the tool stands

Solid foundation: pure converter module, thin CLI transport, stdlib-only, 38 tests, clean
architecture docs. What it is today: "transcript file in → blog post out, via OpenRouter."

What a self-learning professional actually does: watches conference talks / YouTube /
podcasts, and wants to **capture, digest, and retain** what they learned — not only publish
blog posts. The gap between "blog converter" and "learning tool" is the theme of this list.

Each item below has: the problem, a concrete solution proposal, effort (S/M/L), and
priority (P1 = do next, P2 = high value, P3 = nice, YAGNI = deliberately skip).

---

## 1. Output styles beyond "blog post" — the core pivot

**Problem.** One hardcoded system prompt produces one artifact: a blog post. Learners want
study notes, summaries, and review material far more often than publishable posts.

**Proposal.** Add `--style` with a small dict of prompt templates in `converter.py`:

| Style | Output |
|-------|--------|
| `blog` (default) | current behavior |
| `notes` | structured study notes: key concepts, definitions, examples |
| `summary` | TL;DR + 5–10 key takeaways + "who should watch the full talk" |
| `actions` | actionable checklist extracted from the talk |
| `flashcards` | Q&A pairs, one per concept, markdown table (Anki-importable via CSV, see §2) |
| `eli5` | plain-language explanation for studying outside your field |

Implementation: `STYLE_PROMPTS: dict[str, str]` replacing the single `SYSTEM_PROMPT`
constant; `prepare_conversion_request(style="blog")` picks one. ~40 lines, no new deps,
no architecture change. This is the single highest-leverage feature in this document.

**Effort:** S. **Priority: P1.**

## 2. Anki/flashcard export

**Problem.** Retention is the whole point of self-learning; markdown notes alone don't feed
spaced repetition.

**Proposal.** With `--style flashcards`, also support `-o deck.csv`: instruct the model to
emit `Q: … / A: …` lines, parse them with a small regex, write 2-column CSV via stdlib
`csv`. Anki imports that natively. Skip `.apkg` generation (needs genanki dep) — CSV covers it.

**Effort:** S (rides on §1). **Priority: P2.**

## 3. Auto-generated metadata (title, description, tags)

**Problem.** Default title is literally `"Conference Talk"`; frontmatter has no
description or tags. Every real run currently requires `-t` or produces a useless title
and filename (`YYYYMMDD-conference-talk.md`).

**Proposal.** When `-t` is omitted, prepend one cheap metadata call: send the first chunk
with "Return JSON: {title, description, tags[]}". Parse with `json.loads` (with a fallback
to the current defaults on parse failure). Feed the result into frontmatter and the output
filename. One extra API call only when the user didn't supply a title.

**Effort:** S–M. **Priority: P1.**

## 4. Chunk coherence — outline-first two-pass conversion

**Problem.** Chunks are converted independently; the model can't see what came before, so
multi-chunk posts repeat introductions, restate context, and produce inconsistent header
levels. This is the biggest *quality* defect in the current pipeline.

**Proposal (lazy version first).** Include the last ~2 sentences of the previous chunk and
the headers generated so far in each prompt ("Continue from: …; existing sections: …").
Requires making the chunk loop stateful in `cli.py` — sequential already, so trivial.

**Proposal (full version, only if lazy version isn't enough).** Two-pass: pass 1 sends the
cleaned transcript (or a compressed form) asking for a section outline; pass 2 converts
each chunk with the outline as shared context. Costs one extra call, fixes coherence
structurally.

**Effort:** S (lazy) / M (two-pass). **Priority: P1 — ship the lazy version, measure.**

## 5. YouTube as an input source

**Problem.** The #1 source of talks for self-learners is YouTube, and getting a transcript
file out of YouTube is the most annoying step of the current workflow.

**Proposal.** Accept a URL as the positional arg. When it matches a YouTube URL, shell out
to `yt-dlp --write-auto-sub --skip-download` if installed (check with `shutil.which`), read
the resulting `.vtt`, and continue through the existing `parse_vtt` path. No new Python
dependency — `yt-dlp` becomes an *optional* external tool with a clear error message when
missing. Keeps the zero-dependency promise honest.

**Effort:** M. **Priority: P2.**

## 6. Audio input via local Whisper — YAGNI (for now)

**Problem.** Podcasts and recorded meetings arrive as audio, not transcripts.

**Verdict:** skip. Whisper (or an API STT service) drags in heavy dependencies or per-minute
costs, and `yt-dlp`/existing transcript exports cover the dominant sources. Revisit only if
users repeatedly ask "how do I get a transcript in the first place?" Then the answer is a
docs section pointing at `whisper.cpp`, not code.

## 7. Resilient API calls: retry, and per-chunk resume

**Problem.** One 429/502 in chunk 7 of 10 throws away six paid completions and the whole run.
There is no retry; `OPENROUTER_TIMEOUT_SECONDS = 60` can also be tight for long chunks on
slow models.

**Proposal.**
- Retry: wrap `request_openrouter_completion` with 3 attempts, exponential backoff
  (`time.sleep(2 ** attempt)`), retrying only on 429/5xx/URLError. ~10 lines.
- Resume: write each completed section to
  `<output>.partial.json` as it finishes; on rerun with the same output target, load
  completed sections and skip their API calls. Delete the partial file on success. Stdlib
  `json`, ~25 lines.
- Bump timeout to 120s or make it an env var.

**Effort:** S. **Priority: P1 — this is money-losing today, not a nice-to-have.**

## 8. Progress feedback and cost transparency

**Problem.** A 10-chunk run is silent for minutes; users can't tell hung from working, and
have no idea what a run costs.

**Proposal.**
- Print `Processing chunk 3/10…` to stderr in the chunk loop (2 lines).
- OpenRouter responses include a `usage` object; sum `prompt_tokens`/`completion_tokens`
  across calls and print a one-line total at the end. Skip price lookup tables — token
  counts alone let users check pricing themselves.
- `--dry-run`: print the prepared prompts and estimated chunk count without calling the
  API. `prepare_conversion_request` is already pure, so this is ~5 lines in `main()`.

**Effort:** S. **Priority: P1.**

## 9. Format inference and stdin input

**Problem.** `--format srt` for a file named `talk.srt` is redundant ceremony; and you can't
pipe text in (`pbpaste | talk-to-blog -`).

**Proposal.** Default `--format` to the file extension when it's `.srt`/`.vtt` (explicit
flag still wins). Accept `-` as the transcript arg to read stdin. Both are small changes
in `main()`.

**Effort:** S. **Priority: P2.**

## 10. Batch mode

**Problem.** Someone catching up on a conference has 20 transcripts.

**Proposal.** Accept a directory as the positional arg: glob `*.txt|*.srt|*.vtt`, run the
existing pipeline per file (sequentially — rate limits), auto-metadata (§3) naming each
output, print a summary table. Continue past per-file failures, exit non-zero if any failed.

**Effort:** M. **Priority: P3 — a shell loop covers this today; document the shell loop in
the README now, build the flag only if demand shows up.**

## 11. Local/alternative model endpoints (Ollama, LM Studio)

**Problem.** Privacy-conscious learners (work meetings, unreleased material) can't send
transcripts to OpenRouter; others want free local inference.

**Proposal.** The request payload is already OpenAI-chat-format. Add
`OPENROUTER_BASE_URL` env var (default: current URL) and make the API key optional when
the base URL isn't openrouter.ai. That single change makes Ollama
(`http://localhost:11434/v1/chat/completions`), LM Studio, and any OpenAI-compatible
endpoint work with zero new code paths.

**Effort:** S. **Priority: P2 — huge capability-per-line ratio.**

## 12. Custom prompt override

**Problem.** Power users will want their own voice/format, and no built-in style (§1) will
satisfy everyone.

**Proposal.** `--prompt-file path.txt` replaces the system prompt with the file's contents.
One flag, one `read_text`. Do **not** build a templating system, variables, or a prompt
library — a file is the whole feature.

**Effort:** S. **Priority: P2.**

## 13. Frontmatter flexibility

**Problem.** Frontmatter is fixed to `title/author/date` YAML. SSGs commonly want
`tags`, `description`, `draft`, `slug`; some (Hugo) accept TOML.

**Proposal.** Extend `generate_frontmatter` to accept an optional extras dict (fed by §3's
tags/description and a repeatable `--meta key=value` CLI flag). Stay YAML-only — every
major SSG reads YAML frontmatter; TOML support is YAGNI.

**Effort:** S. **Priority: P3 (P2 if §3 ships, since tags/description need somewhere to go).**

## 14. Speaker-aware mode for interviews and panels

**Problem.** `clean_transcript` strips speaker labels unconditionally. For panels, podcasts,
and interviews the *dialogue structure is the content* — stripping it destroys meaning.

**Proposal.** `--keep-speakers` flag that skips the `_SPEAKER_LABEL_RE` pass and switches
the style prompt to "preserve the conversational structure, attribute quotes to speakers."
Also fixes a latent bug: the current regex can eat capitalized non-name phrases at sentence
starts beyond the hardcoded `_NON_SPEAKER_LABELS` allowlist.

**Effort:** S. **Priority: P2.**

## 15. Packaging & distribution polish

**Problem.** A tool for professionals should install like one. Currently: `setup.py`
(deprecated path), no PyPI release, no `--version`, no CI, and a stray
`talk_to_blog.egg-info/` plus `COMPLETION_STATE.md` in the repo root.

**Proposal.**
- Migrate `setup.py` → `pyproject.toml` (mechanical, ~20 lines).
- Publish to PyPI so `pipx install talk-to-blog` works — this is the difference between
  "a repo" and "a tool" for the target audience.
- Add `--version` flag reading `importlib.metadata.version`.
- GitHub Actions: one workflow, `python -m unittest discover tests` on 3.8–3.12.
- `.gitignore` the egg-info; move or delete `COMPLETION_STATE.md`.

**Effort:** S–M. **Priority: P1 for pyproject+PyPI+version; P2 for CI.**

## 16. Things deliberately not on the list (YAGNI)

- **Web UI / TUI** — the CLI is the product; a UI is a different product.
- **Direct publishing** (Ghost/WordPress/dev.to APIs) — output is a markdown file; every
  SSG workflow already knows what to do with a file.
- **Async/parallel chunk requests** — sequential is deliberate (ordering + rate limits);
  resume (§7) removes the main pain of slow runs.
- **A plugin system** for formats/styles — dicts and flags cover the real cardinality.
- **RAG / knowledge-base across talks** — genuinely interesting, genuinely a different
  project.
- **python-dotenv, requests, click, rich** — stdlib versions already exist and work;
  the zero-dependency install story is a feature, keep it.

---

## Suggested sequencing

| Wave | Items | Rationale |
|------|-------|-----------|
| 1 | §7 retry/resume, §8 progress/dry-run, §3 auto-metadata, §15 pyproject+PyPI | Stop losing money, stop being silent, kill the "Conference Talk" default, become installable |
| 2 | §1 output styles, §4 chunk coherence (lazy) | The learning-tool pivot + the biggest quality fix |
| 3 | §11 local endpoints, §12 prompt file, §14 keep-speakers, §9 inference/stdin, §2 flashcard CSV | Small flags, big audience widening |
| 4 | §5 YouTube input, §13 frontmatter extras, §10 batch (if demanded) | Convenience layer once the core is exceptional |

Everything in waves 1–3 preserves the current architecture (pure `converter`, I/O-owning
`cli`) and the zero-dependency install. That constraint is worth defending — it is the
tool's most distinctive engineering property.
