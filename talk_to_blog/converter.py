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
        "You are an expert meeting analyst. Extract only what the transcript supports; never invent, "
        "infer an owner, or upgrade a mention into a choice. Use these Markdown sections, omitting empty ones:\n"
        "## Decisions: something a speaker chose or the group agreed on, stated as settled.\n"
        "## Commitments: someone explicitly took a task on. Format `- [ ] task (owner; due if stated) @ source`.\n"
        "## Open questions: raised and left unresolved or deferred.\n"
        "## Suggestions (not adopted): ideas merely mentioned, proposed, or floated with no stated choice "
        "or agreement. If unsure whether something was chosen, it belongs here.\n"
        "Format every other item `- text (who) @ source`, with a short verbatim quote after it when that "
        "helps verify it. A source is the nearest preceding [HH:MM:SS] marker in the transcript, or the "
        "chunk label (e.g. chunk 2/5) when there are no markers. "
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
_STAMP_INTERVAL_SECONDS = 30
_STAMP_RE = re.compile(r"\[\d{2}:\d{2}:\d{2}\]")
_NON_SPEAKER_LABELS = frozenset({"Note", "Tip", "Warning", "Example", "The API"})
# ponytail: matches YouTube "Show transcript" copy-paste; a content line that is
# only a bare clock time also disappears, acceptable for spoken-word transcripts
_TIMESTAMP_LINE_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ConversionRequest:
    """Prompt payloads and metadata needed to request blog content from an AI model."""

    title: str
    author: str
    pub_date: str
    cleaned_transcript: str
    system_prompt: str
    user_prompts: Tuple[str, ...]


def _stamp(start: str, last: List[float]) -> str:
    """Return a [HH:MM:SS] marker for a cue start, or "" if one was emitted under 30s ago."""
    parts = [0.0] * (3 - len(start.split(":"))) + [float(p.replace(",", ".")) for p in start.split(":")]
    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    if last and 0 <= seconds - last[0] < _STAMP_INTERVAL_SECONDS:
        return ""
    last[:] = [seconds]
    return f"[{int(seconds // 3600):02d}:{int(seconds % 3600 // 60):02d}:{int(seconds % 60):02d}]"


def _carry_stamps(chunks: List[str]) -> List[str]:
    """Open each chunk with the latest earlier marker so its first items have a source."""
    carried: List[str] = []
    last = ""
    for chunk in chunks:
        carried.append(chunk if last == "" or _STAMP_RE.match(chunk) else f"{last} {chunk}")
        found = _STAMP_RE.findall(chunk)
        last = found[-1] if found else last
    return carried


def parse_srt(transcript: str, timestamps: bool = False) -> str:
    """Parse SRT subtitle format and return plain text; optionally keep sparse time markers."""
    if not transcript.strip():
        return ""

    text_lines: List[str] = []
    last: List[float] = []
    for block in re.split(r"\n\s*\n", transcript.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines or not _SRT_TIMESTAMP_RE.match(lines[0]):
            continue
        if timestamps and lines[1:]:
            text_lines.append(_stamp(lines[0].split()[0], last))
        text_lines.extend(lines[1:])
    return " ".join(filter(None, text_lines))


def parse_vtt(transcript: str, timestamps: bool = False) -> str:
    """Parse WebVTT format and return plain text; optionally keep sparse time markers."""
    lines = transcript.strip().split("\n")
    text_lines: List[str] = []
    last: List[float] = []
    skip_header = True
    for line in lines:
        if skip_header:
            if line.strip() == "":
                skip_header = False
            continue
        if "-->" in line:
            if timestamps:
                text_lines.append(_stamp(line.split("-->")[0].strip(), last))
            continue
        if line.strip().isdigit():
            continue
        if line.strip():
            text_lines.append(line.strip())
    return " ".join(filter(None, text_lines))


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
    text = _TIMESTAMP_LINE_RE.sub("", text)
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
    stamped = style == "actions"  # source locations need the cue times other styles discard
    keep_speakers = keep_speakers or stamped  # owners of commitments must survive cleanup
    if transcript_format == "srt":
        text = parse_srt(transcript, timestamps=stamped)
    elif transcript_format == "vtt":
        text = parse_vtt(transcript, timestamps=stamped)
    else:
        text = transcript

    if style not in STYLE_PROMPTS:
        raise ValueError(f"Unsupported style: {style}")
    text = clean_transcript(text, remove_speaker_labels=not keep_speakers)
    resolved_title, resolved_author, resolved_date = _resolve_metadata(title, author, date)
    chunks = chunk_text(text, chunk_size=chunk_size) or [""]
    if stamped:
        chunks = _carry_stamps(chunks)
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
    if keep_speakers:
        user_prompts = tuple(
            prompt
            + "\n\nPreserve the conversational structure and attribute quotes to speakers."
            for prompt in user_prompts
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
    trailing_text = re.split(r"[.!?]", previous_section)[-1].strip()
    ending = trailing_text[-500:] if trailing_text else " ".join(sentences[-2:]).strip()
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
