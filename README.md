# Talk to Blog

A command-line tool that leverages **OpenRouter AI** to intelligently convert conference talk transcripts into polished, structured markdown blog posts.

Unlike traditional text-splitters, `talk-to-blog` dynamically processes raw, messy transcripts (complete with filler words and timestamp artifacts) and instructs LLMs to output coherent, logically structured markdown text, while enforcing a static-site friendly frontmatter header.

## Features

- **AI-Powered Logic**: Uses OpenRouter.ai to access any major LLM (`claude-3-haiku`, `llama-3`, `gpt-4o`, etc.) to structure and rewrite the content.
- **Multiple Transcript Formats**: Extracts text natively from `.txt`, `.srt`, and `.vtt` formats by scrubbing timestamps and headers prior to AI processing.
- **Dynamic AI Model Selection**: Choose your preferred OpenRouter AI Model via a `.env` file or dynamically at runtime via a CLI flag.
- **Frontmatter Generation**: Readily generates YAML frontmatter so the markdown is ready-to-publish for Static Site Generators like Hugo, Jekyll, or NextJS.
- **Customizable Overrides**: Specify Authors, Titles, and Publication Dates effortlessly.
- **Zero-Dependency Architecture**: Built using only the Python standard library. No bloated third-party installations.

## Installation

Because this tool is built cleanly using standard native libraries, installation is incredibly simple:

```bash
# Clone the repository
git clone https://github.com/ryan258/talk-to-blog.git
cd talk-to-blog

# Install in development mode natively
pip install -e .
```

## Configuration (Environment Variables)

`talk-to-blog` connects to the AI exclusively via OpenRouter to maximize model flexibility.

Create a `.env` file in the directory where you plan to execute the command:

```bash
# .env
OPENROUTER_API_KEY="sk-or-v1-..."
OPENROUTER_MODEL="meta-llama/llama-3-8b-instruct" # Optional: define your default fallback model
```

> **Note:** The application reads `.env` natively without `python-dotenv`. It looks first next to the transcript file, then in the current working directory, and finally falls back to real environment variables for missing keys. Make sure not to commit the `.env` file.

## Usage

### Basic Execution

By default, the script writes each run into an `output/` directory next to the transcript using the pattern `YYYYMMDD-talk-title.md`. Use `-o` to override the file path, or `-o -` to write to `stdout`.

```bash
# Convert a plain text transcript and write to output/20240510-my-talk.md
talk-to-blog transcript.txt -t "My Talk" -d "2024-05-10"

# Override the AI model dynamically via the CLI and force stdout
talk-to-blog transcript.txt -m anthropic/claude-3-opus -o -
```

### Transcript Formats

If you are using subtitles (`.srt` or `.vtt`), specify the format so the tool scrubs timestamps before making AI calls:

```bash
talk-to-blog talk.srt --format srt -o blog.md
talk-to-blog talk.vtt --format vtt -t "An Example Conference Talk" -o blog.md
```

### Full Options Command

```bash
talk-to-blog transcript.txt \
  -f txt \
  -m anthropic/claude-3-haiku \
  -t "The Future of Python Programming" \
  -a "Jane Doe" \
  -d "2024-05-10" \
  -o my-blog-post.md
```

### Command Reference

| Flag | Name | Description | Default |
|------|------|-------------|---------|
| `transcript` | Path | Positional argument targeting the transcript file. | **Required** |
| `-o` | `--output` | Output file path override. Use `-` to write to stdout. | `transcript_dir/output/YYYYMMDD-talk-title.md` |
| `-f` | `--format` | Parse the file as `txt`, `srt`, or `vtt`. | `txt` |
| `-m` | `--model` | OpenRouter Model identifier (overrides `.env`). | Fallbacks to `.env` |
|      | `--chunk-size` | Approximate words per AI section request. Large transcripts are split across multiple prompts. | `500` |
| `-t` | `--title` | The blog post title generated in the frontmatter and H1. | `Conference Talk` |
| `-a` | `--author` | The author's name inside the frontmatter. | `Speaker` |
| `-d` | `--date` | The publication date generated in the frontmatter. | *Today's local date* |
|      | `--no-frontmatter` | Action flag to bypass generating the YAML header entirely. | `False` |

## Advanced Architecture Context

Because this project aims to act as a strict integration layer, developers looking to contribute should review the documentation enclosed in `docs/architecture/`. The CLI owns filesystem, environment, and OpenRouter HTTP calls; `talk_to_blog.converter` remains a pure planning/composition module.

## Development & Testing

```bash
# Run the test suite natively
python3 -m unittest discover tests
```

## License

MIT License
