#!/usr/bin/env python3
"""Core conversion logic for transforming transcripts into blog posts."""
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional


def parse_srt(transcript: str) -> str:
    """Parse SRT subtitle format and return plain text."""
    lines = transcript.strip().split("\n")
    text_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit():
            # Skip index line
            i += 1
            # Check if next line is a timestamp line
            if i < len(lines) and '-->' in lines[i]:
                # Skip timestamp line
                i += 1
            # Collect text lines until empty line or end
            while i < len(lines) and lines[i].strip():
                # Skip if we encounter another index line (shouldn't happen in well-formed SRT)
                if lines[i].strip().isdigit():
                    break
                text_lines.append(lines[i].strip())
                i += 1
        i += 1
    return " ".join(text_lines)


def parse_vtt(transcript: str) -> str:
    """Parse WebVTT format and return plain text."""
    lines = transcript.strip().split("\n")
    text_lines = []
    skip_header = True
    for line in lines:
        if skip_header:
            if line.strip() == "":
                skip_header = False
            continue
        # Skip timestamp lines
        if "-->" in line:
            continue
        # Skip cue identifiers (numbers)
        if line.strip().isdigit():
            continue
        if line.strip():
            text_lines.append(line.strip())
    return " ".join(text_lines)


def clean_transcript(text: str) -> str:
    """Clean raw transcript text."""
    # Remove speaker labels like "Speaker 1:" or "John:"
    text = re.sub(r"^[A-Za-z0-9_]+:\s*", "", text, flags=re.MULTILINE)
    # Remove filler words
    fillers = ["um", "uh", "like", "you know", "so", "actually", "basically"]
    for filler in fillers:
        text = re.sub(r"\b" + filler + r"\b", "", text, flags=re.IGNORECASE)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    """Split text into chunks of approximately chunk_size words."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for word in words:
        current_chunk.append(word)
        current_word_count += 1
        if current_word_count >= chunk_size:
            # Try to break at sentence boundary
            chunk_text = " ".join(current_chunk)
            # Find last sentence boundary
            last_period = chunk_text.rfind(".")
            if last_period > len(chunk_text) * 0.7:  # If period is in last 30%
                chunks.append(chunk_text[:last_period + 1].strip())
                remaining = chunk_text[last_period + 1:].strip()
                if remaining:
                    current_chunk = [remaining]
                    current_word_count = len(remaining.split())
                else:
                    current_chunk = []
                    current_word_count = 0
            else:
                chunks.append(chunk_text)
                current_chunk = []
                current_word_count = 0
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


def generate_frontmatter(title: str, author: str, pub_date: str) -> str:
    """Generate YAML frontmatter for blog post."""
    return f"""---
title: "{title}"
author: "{author}"
date: "{pub_date}"
---

"""


def convert_transcript_to_blog(
    transcript: str,
    transcript_format: str = "txt",
    title: Optional[str] = None,
    author: Optional[str] = None,
    date: Optional[str] = None,
    include_frontmatter: bool = True,
    chunk_size: int = 500
) -> str:
    """Convert transcript text to blog post format."""
    # Parse based on format
    if transcript_format == "srt":
        text = parse_srt(transcript)
    elif transcript_format == "vtt":
        text = parse_vtt(transcript)
    else:  # txt
        text = transcript
    
    # Clean the text
    text = clean_transcript(text)
    
    # Generate title if not provided
    if not title:
        title = "Conference Talk"
    
    # Set defaults
    if not author:
        author = "Speaker"
    if not date:
        pub_date = datetime.now().strftime("%Y-%m-%d")
    else:
        pub_date = date
    
    # Chunk the text
    chunks = chunk_text(text, chunk_size)
    
    # Build blog post
    blog_parts = []
    if include_frontmatter:
        blog_parts.append(generate_frontmatter(title, author, pub_date))
    
    blog_parts.append(f"# {title}\n\n")
    
    for i, chunk in enumerate(chunks, 1):
        blog_parts.append(f"## Part {i}\n\n{chunk}\n\n")
    
    return "".join(blog_parts)