#!/usr/bin/env python3
"""Command-line interface for talk-to-blog converter."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .converter import convert_transcript_to_blog, prepare_conversion_request

DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3-8b-instruct"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT_SECONDS = 60
DEFAULT_OUTPUT_DIR_NAME = "output"


def positive_int(value: str) -> int:
    """Argparse type that accepts positive integers only."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("chunk size must be a positive integer")
    return parsed


def load_env(env_paths: Optional[Sequence[Path]] = None) -> Dict[str, str]:
    """Load .env values from the provided paths and fill missing keys from the environment."""
    env_vars: Dict[str, str] = {}

    candidate_paths = tuple(env_paths) if env_paths is not None else (Path.cwd() / ".env",)
    seen_paths = set()
    for candidate_path in candidate_paths:
        env_path = Path(candidate_path)
        if env_path in seen_paths:
            continue
        seen_paths.add(env_path)
        if not env_path.exists():
            continue
        try:
            content = env_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars.setdefault(key.strip(), value.strip().strip("'\""))

    for key, value in os.environ.items():
        env_vars.setdefault(key, value)
    return env_vars


def _slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "conference-talk"


def _output_date_fragment(pub_date: str) -> str:
    try:
        return datetime.strptime(pub_date, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        digits = re.sub(r"\D", "", pub_date)
        if len(digits) >= 8:
            return digits[:8]
        return "undated"


def resolve_output_path(
    transcript_path: Path,
    output_arg: Optional[str],
    title: str,
    pub_date: str,
) -> Optional[Path]:
    """Resolve the final output path. Return None when stdout is requested."""
    if output_arg == "-":
        return None

    filename = f"{_output_date_fragment(pub_date)}-{_slugify_title(title)}.md"
    if output_arg:
        return Path(output_arg).expanduser()
    return transcript_path.parent / DEFAULT_OUTPUT_DIR_NAME / filename


def _extract_openrouter_error(payload: Dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        if message:
            return str(message)
    if isinstance(error, str) and error:
        return error

    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return "Unexpected OpenRouter response payload"


def extract_openrouter_content(payload: Dict[str, Any]) -> str:
    """Extract model output from an OpenRouter response payload."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(_extract_openrouter_error(payload))

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("OpenRouter returned an invalid choices payload")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenRouter response is missing message content")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter response is missing text content")

    return content.strip()


def request_openrouter_completion(api_key: str, ai_model: str, system_prompt: str, user_prompt: str) -> str:
    """Send a single prompt to OpenRouter and return the generated content."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ryan258/talk-to-blog",
        "X-Title": "Talk-to-Blog App",
    }
    payload = {
        "model": ai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=OPENROUTER_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(error_body)
            detail = _extract_openrouter_error(error_payload)
        except json.JSONDecodeError:
            detail = error_body.strip() or error.reason
        raise ValueError(f"OpenRouter request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"Failed to communicate with OpenRouter API: {error.reason}") from error

    try:
        response_payload = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise ValueError(f"Failed to parse OpenRouter response: {error}") from error

    return extract_openrouter_content(response_payload)


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Convert conference talk transcripts into blog posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s transcript.txt
  %(prog)s transcript.srt --format srt -o blog.md
  %(prog)s transcript.vtt --format vtt -t "My Talk Title" -a "Jane Doe"
  %(prog)s transcript.txt -o -
        """,
    )
    parser.add_argument("transcript", help="Path to transcript file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path. Defaults to transcript_dir/output/YYYYMMDD-talk-title.md; use '-' for stdout",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["txt", "srt", "vtt"],
        default="txt",
        help="Transcript format (default: txt)",
    )
    parser.add_argument("-t", "--title", help="Blog post title (default: Conference Talk)")
    parser.add_argument("-a", "--author", help="Author name (default: 'Speaker')")
    parser.add_argument("-d", "--date", help="Publication date (default: today)")
    parser.add_argument("--no-frontmatter", action="store_true", help="Omit YAML frontmatter")
    parser.add_argument(
        "--chunk-size",
        type=positive_int,
        default=500,
        help="Approximate words per AI section request (default: 500)",
    )
    parser.add_argument("-m", "--model", help="OpenRouter AI model to use (overrides env and .env)")

    args = parser.parse_args()

    transcript_path = Path(args.transcript).expanduser()
    if not transcript_path.exists():
        print(f"Error: File '{transcript_path}' not found", file=sys.stderr)
        sys.exit(1)

    transcript_path = transcript_path.resolve()
    env_vars = load_env((transcript_path.parent / ".env", Path.cwd() / ".env"))

    api_key = env_vars.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    ai_model = args.model or env_vars.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    resolved_date = args.date or datetime.now().strftime("%Y-%m-%d")

    try:
        transcript_text = transcript_path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"Error reading file: {error}", file=sys.stderr)
        sys.exit(1)

    try:
        conversion_request = prepare_conversion_request(
            transcript_text,
            transcript_format=args.format,
            title=args.title,
            author=args.author,
            date=resolved_date,
            chunk_size=args.chunk_size,
        )
        # Keep chunk requests sequential for stable ordering and to avoid bursty rate-limit behavior.
        ai_sections = [
            request_openrouter_completion(
                api_key=api_key,
                ai_model=ai_model,
                system_prompt=conversion_request.system_prompt,
                user_prompt=user_prompt,
            )
            for user_prompt in conversion_request.user_prompts
        ]
        blog_content = convert_transcript_to_blog(
            ai_sections,
            title=conversion_request.title,
            author=conversion_request.author,
            date=resolved_date,
            include_frontmatter=not args.no_frontmatter,
        )
    except ValueError as error:
        print(f"Error converting transcript: {error}", file=sys.stderr)
        sys.exit(1)

    output_path = resolve_output_path(
        transcript_path=transcript_path,
        output_arg=args.output,
        title=conversion_request.title,
        pub_date=resolved_date,
    )

    if output_path is None:
        print(blog_content)
        return

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(blog_content, encoding="utf-8")
        print(f"Blog post written to {output_path}", file=sys.stderr)
    except OSError as error:
        print(f"Error writing output file: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
