#!/usr/bin/env python3
"""Pure conversion logic for transforming transcripts into blog posts."""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

DEFAULT_TITLE = "Conference Talk"
DEFAULT_AUTHOR = "Speaker"
SYSTEM_PROMPT = (
    "You are an expert technical writer. Convert the provided conference transcript "
    "into a structured, engaging markdown blog post. Preserve the original meaning and core logic "
    "but improve flow, grammar, and engagement. Add appropriate markdown headers where logical shifts occur. "
    "Do NOT include frontmatter or the top-level title heading; return body content only."
)
STYLE_PROMPTS: Dict[str, str] = {
    "blog": SYSTEM_PROMPT,
    "notes": (
        "You are an expert educator. Turn the transcript into concise Markdown study notes. "
        "Use headings, key concepts, definitions, examples, and open questions where useful. "
        "Preserve meaning. Do not include frontmatter or a top-level title."
    ),
    "summary": (
        "You are an expert technical editor. Summarize the transcript in Markdown with a TL;DR, "
        "5–10 key takeaways, and who should watch the full talk. Do not include frontmatter or a top-level title."
    ),
    "actions": (
        "You are an expert learning coach. Extract a Markdown action plan from the transcript: "
        "specific, attributable next steps and practical checklists. Do not invent actions. "
        "Do not include frontmatter or a top-level title."
    ),
    "flashcards": (
        "Create durable study flashcards from the transcript. Return only Q: question / A: answer pairs, "
        "one pair per concept, with no Markdown table, title, or frontmatter. Keep answers self-contained."
    ),
    "eli5": (
        "Explain the transcript in approachable Markdown for an intelligent beginner outside this field. "
        "Use concrete analogies without losing important nuance. Do not include frontmatter or a top-level title."
    ),
}

_SRT_TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
_SPEAKER_LABEL_RE = re.compile(
    r"(?P<prefix>^|[.!?\n]\s*)(?P<label>(?:[Ss]peaker\s*\d+|[A-Z][A-Za-z0-9_]*(?:\s+[A-Z0-9_][A-Za-z0-9_]*){0,2})):\s+(?=\S)",
    flags=re.MULTILINE,
)
_CLAUSE_FILLER_RE = re.compile(
    r"(^|[.!?\n]\s*|,\s*)(?:um|uh|you know|like|actually|basically)\b(?:,\s*)?",
    flags=re.IGNORECASE | re.MULTILINE,
)
_INLINE_FILLER_RE = re.compile(
    r"\b(?:actually|basically)\b(?=\s+(?:a|an|the|this|that|these|those|it|we|you|i|he|she|they)\b)",
    flags=re.IGNORECASE,
)
_LEADING_SO_FILLER_RE = re.compile(
    r"(^|[.!?\n]\s*)so\b(?=(?:,\s*|\s+(?:um|uh|you know|like|actually|basically)\b))",
    flags=re.IGNORECASE | re.MULTILINE,
)
_NON_SPEAKER_LABELS = frozenset({"Note", "Tip", "Warning", "Example", "The API"})


@dataclass(frozen=True)
class ConversionRequest:
    """Prompt payloads and metadata needed to request blog content from an AI model."""

    title: str
    author: str
    pub_date: str
    cleaned_transcript: str
    system_prompt: str
    user_prompts: Tuple[str, ...]


def parse_srt(transcript: str) -> str:
    """Parse SRT subtitle format and return plain text."""
    if not transcript.strip():
        return ""

    text_lines: List[str] = []
    for block in re.split(r"\n\s*\n", transcript.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines or not _SRT_TIMESTAMP_RE.match(lines[0]):
            continue
        text_lines.extend(lines[1:])
    return " ".join(text_lines)


def parse_vtt(transcript: str) -> str:
    """Parse WebVTT format and return plain text."""
    lines = transcript.strip().split("\n")
    text_lines: List[str] = []
    skip_header = True
    for line in lines:
        if skip_header:
            if line.strip() == "":
                skip_header = False
            continue
        if "-->" in line:
            continue
        if line.strip().isdigit():
            continue
        if line.strip():
            text_lines.append(line.strip())
    return " ".join(text_lines)


def _replace_speaker_label(match: re.Match) -> str:
    label = match.group("label")
    if label in _NON_SPEAKER_LABELS:
        return match.group(0)
    return match.group("prefix")


def _replace_clause_filler(match: re.Match) -> str:
    prefix = match.group(1)
    if prefix.startswith(","):
        return " "
    return prefix


def clean_transcript(text: str, remove_speaker_labels: bool = True) -> str:
    """Clean raw transcript text."""
    if remove_speaker_labels:
        text = _SPEAKER_LABEL_RE.sub(_replace_speaker_label, text)

    previous = None
    while text != previous:
        previous = text
        text = _LEADING_SO_FILLER_RE.sub(r"\1", text)
        text = _CLAUSE_FILLER_RE.sub(_replace_clause_filler, text)
        text = re.sub(r"\s+", " ", text).strip()

    text = _INLINE_FILLER_RE.sub("", text)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    """Split text into chunks of approximately chunk_size words."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    words = text.split()
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_word_count = 0

    for word in words:
        current_chunk.append(word)
        current_word_count += 1
        if current_word_count >= chunk_size:
            candidate_chunk = " ".join(current_chunk)
            last_period = candidate_chunk.rfind(".")
            if last_period > len(candidate_chunk) * 0.7:
                chunks.append(candidate_chunk[: last_period + 1].strip())
                remaining = candidate_chunk[last_period + 1 :].strip()
                if remaining:
                    current_chunk = [remaining]
                    current_word_count = len(remaining.split())
                else:
                    current_chunk = []
                    current_word_count = 0
            else:
                chunks.append(candidate_chunk)
                current_chunk = []
                current_word_count = 0

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _yaml_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_yaml_quote(str(item)) for item in value) + "]"
    return _yaml_quote(str(value))


def generate_frontmatter(
    title: str,
    author: str,
    pub_date: str,
    extras: Optional[Mapping[str, Any]] = None,
) -> str:
    """Generate YAML frontmatter for blog post."""
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"author: {_yaml_quote(author)}",
        f"date: {_yaml_quote(pub_date)}",
    ]
    for key, value in (extras or {}).items():
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key):
            lines.append(f"{key}: {_yaml_value(value)}")
    return "\n".join(lines) + "\n---\n\n"


def _resolve_metadata(
    title: Optional[str],
    author: Optional[str],
    date: Optional[str],
) -> Tuple[str, str, str]:
    resolved_title = title or DEFAULT_TITLE
    resolved_author = author or DEFAULT_AUTHOR
    resolved_date = date or ""
    return resolved_title, resolved_author, resolved_date


def _build_user_prompt(
    title: str,
    author: str,
    pub_date: str,
    transcript_chunk: str,
    chunk_index: int,
    total_chunks: int,
) -> str:
    if total_chunks == 1:
        chunk_note = "Convert the full transcript into polished markdown sections."
    else:
        chunk_note = (
            f"Convert chunk {chunk_index} of {total_chunks} into polished markdown sections "
            "that can be concatenated with the rest of the post without repeating the title."
        )

    return (
        f"Title: {title}\n"
        f"Author: {author}\n"
        f"Date: {pub_date}\n"
        f"Chunk: {chunk_index}/{total_chunks}\n\n"
        f"{chunk_note}\n"
        "Do not include frontmatter or the top-level title heading.\n\n"
        f"Transcript:\n{transcript_chunk}"
    )


def prepare_conversion_request(
    transcript: str,
    transcript_format: str = "txt",
    title: Optional[str] = None,
    author: Optional[str] = None,
    date: Optional[str] = None,
    chunk_size: int = 500,
    style: str = "blog",
    keep_speakers: bool = False,
    system_prompt: Optional[str] = None,
) -> ConversionRequest:
    """Parse, clean, chunk, and package transcript content for an AI request."""
    if transcript_format == "srt":
        text = parse_srt(transcript)
    elif transcript_format == "vtt":
        text = parse_vtt(transcript)
    else:
        text = transcript

    if style not in STYLE_PROMPTS:
        raise ValueError(f"Unsupported style: {style}")
    text = clean_transcript(text, remove_speaker_labels=not keep_speakers)
    resolved_title, resolved_author, resolved_date = _resolve_metadata(title, author, date)
    chunks = chunk_text(text, chunk_size=chunk_size) or [""]
    user_prompts = tuple(
        _build_user_prompt(
            resolved_title,
            resolved_author,
            resolved_date,
            chunk,
            chunk_index=index,
            total_chunks=len(chunks),
        )
        for index, chunk in enumerate(chunks, start=1)
    )
    return ConversionRequest(
        title=resolved_title,
        author=resolved_author,
        pub_date=resolved_date,
        cleaned_transcript=text,
        system_prompt=system_prompt or STYLE_PROMPTS[style],
        user_prompts=user_prompts,
    )


def with_continuity_context(user_prompt: str, previous_section: str) -> str:
    """Attach bounded, model-generated continuity hints to a later chunk prompt."""
    headings = re.findall(r"^#{2,6}\s+(.+?)\s*$", previous_section, flags=re.MULTILINE)
    sentences = re.findall(r"[^.!?]+[.!?]", previous_section)
    ending = " ".join(sentences[-2:]).strip() or previous_section.strip()[-500:]
    context_parts = []
    if headings:
        context_parts.append("Existing section headings: " + "; ".join(headings[-8:]))
    if ending:
        context_parts.append("Previous section ending: " + ending[-500:])
    if not context_parts:
        return user_prompt
    return user_prompt + "\n\nContinuity context (do not repeat it verbatim):\n" + "\n".join(context_parts)


def extract_flashcards(content: str) -> List[Tuple[str, str]]:
    """Parse the deliberately simple Q:/A: flashcard interchange format."""
    cards: List[Tuple[str, str]] = []
    pattern = re.compile(r"^Q:\s*(.+?)\s*\nA:\s*(.+?)(?=\n\s*Q:|\Z)", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(content.strip()):
        question = re.sub(r"\s+", " ", match.group(1)).strip()
        answer = re.sub(r"\s+", " ", match.group(2)).strip()
        if question and answer:
            cards.append((question, answer))
    return cards


def convert_transcript_to_blog(
    ai_content: Union[str, Sequence[str]],
    title: Optional[str] = None,
    author: Optional[str] = None,
    date: Optional[str] = None,
    include_frontmatter: bool = True,
    frontmatter_extras: Optional[Mapping[str, Any]] = None,
) -> str:
    """Compose the final blog post from AI-generated markdown body content."""
    resolved_title, resolved_author, resolved_date = _resolve_metadata(title, author, date)

    if isinstance(ai_content, str):
        sections = [ai_content.strip()]
    else:
        sections = [section.strip() for section in ai_content if section and section.strip()]

    blog_parts: List[str] = []
    if include_frontmatter:
        blog_parts.append(generate_frontmatter(resolved_title, resolved_author, resolved_date, frontmatter_extras))

    blog_parts.append(f"# {resolved_title}\n\n")
    blog_parts.append("\n\n".join(sections))
    return "".join(blog_parts)
