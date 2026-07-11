# Talk to Blog

Turn conference talks, interviews, and YouTube captions into useful Markdown learning artifacts. `talk-to-blog` uses any OpenAI-compatible chat-completions endpoint while keeping its core dependency-free.

## Install

```bash
pipx install talk-to-blog             # after the project is published to PyPI
# or, from a clone:
python -m pip install -e .
```

## Configure

Create `.env` next to a transcript or in the current directory:

```bash
OPENROUTER_API_KEY="sk-or-v1-..."
OPENROUTER_MODEL="meta-llama/llama-3-8b-instruct"
```

For Ollama, LM Studio, or another compatible service, set `OPENAI_BASE_URL` (or the legacy-compatible `OPENROUTER_BASE_URL`) to its full chat-completions endpoint. A key is required only for OpenRouter; other services decide whether to require one.

## Examples

```bash
# A default blog post; title, description, and tags are generated when title is omitted.
talk-to-blog talk.vtt

# Learning artifacts.
talk-to-blog talk.srt --style notes
talk-to-blog talk.txt --style summary -o -
talk-to-blog interview.txt --style actions --keep-speakers

# Anki-ready CSV (the model emits validated Q:/A: pairs).
talk-to-blog talk.txt --style flashcards -o deck.csv

# Pipelines, formats, batches, and optional YouTube captions.
pbpaste | talk-to-blog - --style eli5 -o -
talk-to-blog conference-transcripts/ -o learning-output/
talk-to-blog 'https://www.youtube.com/watch?v=example' --style notes

# Inspect prompts without sending transcript data to an API.
talk-to-blog talk.txt --style notes --dry-run
```

`yt-dlp` is optional and is only needed for YouTube URLs. It must be installed separately and captions must be available.

## Reliable long runs

Multi-chunk work is sequential to preserve ordering and avoid rate-limit bursts. Retryable network, 429, and 5xx failures are retried three times. Each successful chunk is stored in a fingerprinted `.partial.json` file next to its output, and a matching rerun resumes automatically. The partial file is deleted on success.

Progress and aggregate prompt/completion token counts are written to stderr. Token counts are not price estimates; check your chosen provider's pricing.

## Command reference

| Option | Purpose |
| --- | --- |
| `--style` | `blog` (default), `notes`, `summary`, `actions`, `flashcards`, or `eli5` |
| `-f`, `--format` | `txt`, `srt`, or `vtt`; subtitle formats are inferred from the extension |
| `--keep-speakers` | Preserve dialogue attribution for panels and interviews |
| `--prompt-file PATH` | Replace the selected style prompt with your own prompt |
| `--endpoint URL` | Override the OpenAI-compatible chat-completions endpoint |
| `--timeout SECONDS` | API timeout; default 120 seconds |
| `--dry-run` | Print prepared prompts without loading credentials or calling an API |
| `--meta KEY=VALUE` | Add YAML frontmatter metadata; repeat as needed |
| `-o`, `--output` | Output file, batch-output directory, or `-` for stdout |
| `--version` | Print the installed version |

## Development

```bash
python3 -m unittest discover tests
```

The CLI owns filesystem, environment, subprocess, and HTTP I/O. The converter remains pure, which keeps parsing, prompt preparation, and output composition fast to test.
