# Talk to Blog

A command-line tool that converts conference talk transcripts into structured blog posts.

## Features

- Supports multiple transcript formats (plain text, SRT, VTT)
- Automatically cleans transcripts (removes speaker labels, filler words)
- Splits long talks into logical sections
- Generates YAML frontmatter for static site generators
- Customizable title, author, and date

## Installation

```bash
pip install -e .
```

## Usage

### Basic usage

```bash
# Convert a plain text transcript
talk-to-blog transcript.txt -o blog.md

# Convert an SRT subtitle file
talk-to-blog talk.srt --format srt -o blog.md

# Convert a WebVTT file with custom title and author
talk-to-blog talk.vtt --format vtt -t "My Conference Talk" -a "Jane Doe" -o blog.md
```

### Options

- `-o, --output`: Output file path (default: stdout)
- `-f, --format`: Transcript format: txt, srt, or vtt (default: txt)
- `-t, --title`: Blog post title (default: "Conference Talk")
- `-a, --author`: Author name (default: "Speaker")
- `-d, --date`: Publication date (default: today)
- `--no-frontmatter`: Omit YAML frontmatter
- `--chunk-size`: Approximate words per section (default: 500)

## Example

Given a transcript file `my-talk.txt`:

```
Hello everyone. Today I want to talk about Python. Python is a great language. It's used for web development, data science, and automation.
```

Running:
```bash
talk-to-blog my-talk.txt -t "Python Overview" -a "John Doe" -o blog.md
```

Produces `blog.md`:

```markdown
---
title: "Python Overview"
author: "John Doe"
date: "2024-01-15"
---

# Python Overview

## Part 1

Hello everyone. Today I want to talk about Python. Python is a great language. It's used for web development, data science, and automation.
```

## Development

```bash
# Install in development mode
pip install -e .

# Run tests
python -m unittest discover tests
```

## License

MIT