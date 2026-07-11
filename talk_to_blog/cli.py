#!/usr/bin/env python3
"""Command-line interface for talk-to-blog converter."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .converter import (
    STYLE_PROMPTS,
    convert_transcript_to_blog,
    extract_flashcards,
    prepare_conversion_request,
    with_continuity_context,
)

DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3-8b-instruct"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT_SECONDS = 120
DEFAULT_OUTPUT_DIR_NAME = "output"
METADATA_SYSTEM_PROMPT = "Return only valid JSON with title, description, and tags (a list of short strings)."


@dataclass(frozen=True)
class CompletionResult:
    content: str
    usage: Mapping[str, Any]


class RequestError(ValueError):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("chunk size must be a positive integer")
    return parsed


def load_env(env_paths: Optional[Sequence[Path]] = None) -> Dict[str, str]:
    """Load .env values, preserving the first configured value for each key."""
    env_vars: Dict[str, str] = {}
    for env_path in dict.fromkeys(env_paths or (Path.cwd() / ".env",)):
        if not env_path.exists():
            continue
        try:
            content = env_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars.setdefault(key.strip(), value.strip().strip("'\""))
    for key, value in os.environ.items():
        env_vars.setdefault(key, value)
    return env_vars


def _slugify_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "conference-talk"


def _output_date_fragment(pub_date: str) -> str:
    try:
        return datetime.strptime(pub_date, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        digits = re.sub(r"\D", "", pub_date)
        return digits[:8] if len(digits) >= 8 else "undated"


def resolve_output_path(transcript_path: Optional[Path], output_arg: Optional[str], title: str, pub_date: str) -> Optional[Path]:
    if output_arg == "-":
        return None
    filename = f"{_output_date_fragment(pub_date)}-{_slugify_title(title)}.md"
    if output_arg:
        return Path(output_arg).expanduser()
    base = transcript_path.parent if transcript_path else Path.cwd()
    return base / DEFAULT_OUTPUT_DIR_NAME / filename


def infer_transcript_format(transcript_path: Optional[Path], explicit_format: Optional[str]) -> str:
    if explicit_format:
        return explicit_format
    return transcript_path.suffix.lower().lstrip(".") if transcript_path and transcript_path.suffix.lower() in {".srt", ".vtt"} else "txt"


def _extract_openrouter_error(payload: Dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "Unexpected API error")
    if isinstance(error, str) and error:
        return error
    return str(payload.get("message") or "Unexpected API response payload")


def extract_openrouter_content(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError(_extract_openrouter_error(payload))
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter response is missing text content")
    return content.strip()


def request_openrouter_completion(
    api_key: str, ai_model: str, system_prompt: str, user_prompt: str,
    endpoint: str = OPENROUTER_URL, timeout: int = OPENROUTER_TIMEOUT_SECONDS,
) -> CompletionResult:
    """Send one OpenAI-compatible chat completion request."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if urllib.parse.urlparse(endpoint).netloc == "openrouter.ai":
        headers.update({"HTTP-Referer": "https://github.com/ryan258/talk-to-blog", "X-Title": "Talk-to-Blog App"})
    data = json.dumps({"model": ai_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            detail = _extract_openrouter_error(json.loads(body))
        except json.JSONDecodeError:
            detail = body.strip() or str(error.reason)
        raise RequestError(f"OpenRouter request failed ({error.code}): {detail}", retryable=error.code == 429 or error.code >= 500) from error
    except urllib.error.URLError as error:
        raise RequestError(f"Failed to communicate with API: {error.reason}", retryable=True) from error
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RequestError(f"Failed to parse API response: {error}") from error
    return CompletionResult(extract_openrouter_content(payload), payload.get("usage") if isinstance(payload.get("usage"), dict) else {})


def request_completion_with_retry(api_key: str, ai_model: str, system_prompt: str, user_prompt: str, *, endpoint: str = OPENROUTER_URL, timeout: int = OPENROUTER_TIMEOUT_SECONDS, attempts: int = 3) -> CompletionResult:
    for attempt in range(attempts):
        try:
            return _as_completion_result(request_openrouter_completion(
                api_key=api_key,
                ai_model=ai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                endpoint=endpoint,
                timeout=timeout,
            ))
        except RequestError as error:
            if not error.retryable or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def parse_metadata_response(content: str) -> Dict[str, Any]:
    content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip())
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Metadata response must be a JSON object")
    result: Dict[str, Any] = {}
    for key in ("title", "description"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            result[key] = payload[key].strip()
    if isinstance(payload.get("tags"), list):
        result["tags"] = [str(tag).strip() for tag in payload["tags"] if str(tag).strip()][:12]
    return result


def build_run_fingerprint(transcript: str, model: str, system_prompt: str, chunk_size: int, style: str) -> str:
    data = json.dumps({"transcript": transcript, "model": model, "system_prompt": system_prompt, "chunk_size": chunk_size, "style": style}, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def load_partial_sections(path: Path, fingerprint: str) -> List[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        sections = payload.get("sections")
        if payload.get("fingerprint") == fingerprint and isinstance(sections, list) and all(isinstance(item, str) for item in sections):
            return sections
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_partial_sections(path: Path, fingerprint: str, sections: Sequence[str]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"fingerprint": fingerprint, "sections": list(sections)}, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_meta_arguments(values: Sequence[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --meta value {value!r}; use key=value")
        key, raw = value.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key):
            raise ValueError(f"Invalid metadata key: {key}")
        result[key] = raw
    return result


def _as_completion_result(value: Any) -> CompletionResult:
    return value if isinstance(value, CompletionResult) else CompletionResult(str(value), {})


def convert_one(transcript_text: str, transcript_path: Optional[Path], args: argparse.Namespace, env_vars: Mapping[str, str]) -> Tuple[str, Optional[Path], Dict[str, int]]:
    endpoint = args.endpoint or env_vars.get("OPENROUTER_BASE_URL") or env_vars.get("OPENAI_BASE_URL") or OPENROUTER_URL
    api_key = env_vars.get("OPENROUTER_API_KEY", "")
    if not args.dry_run and not api_key and urllib.parse.urlparse(endpoint).netloc == "openrouter.ai":
        raise ValueError("OPENROUTER_API_KEY not found in environment or .env")
    model = args.model or env_vars.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    pub_date = args.date or datetime.now().strftime("%Y-%m-%d")
    system_prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else None
    transcript_format = infer_transcript_format(transcript_path, args.format)
    provisional = prepare_conversion_request(transcript_text, transcript_format, args.title, args.author, pub_date, args.chunk_size, args.style, args.keep_speakers, system_prompt)
    metadata: Dict[str, Any] = {}
    metadata_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not args.title and not args.dry_run:
        try:
            response = request_completion_with_retry(api_key, model, METADATA_SYSTEM_PROMPT, provisional.cleaned_transcript[:6000], endpoint=endpoint, timeout=args.timeout)
            metadata_result = _as_completion_result(response)
            metadata = parse_metadata_response(metadata_result.content)
            for key in metadata_usage:
                metadata_usage[key] += int(metadata_result.usage.get(key, 0) or 0)
        except (RequestError, ValueError):
            metadata = {}
    request = prepare_conversion_request(transcript_text, transcript_format, metadata.get("title") or args.title, args.author, pub_date, args.chunk_size, args.style, args.keep_speakers, system_prompt)
    output_path = resolve_output_path(transcript_path, args.output, request.title, pub_date)
    if args.dry_run:
        print(f"Prepared {len(request.user_prompts)} chunk(s), style={args.style}, endpoint={endpoint}", file=sys.stderr)
        print("\n\n".join(request.user_prompts))
        return "", output_path, {}
    fingerprint = build_run_fingerprint(request.cleaned_transcript, model, request.system_prompt, args.chunk_size, args.style)
    partial_path = output_path.with_name(output_path.name + ".partial.json") if output_path else None
    if partial_path:
        partial_path.parent.mkdir(parents=True, exist_ok=True)
    sections = load_partial_sections(partial_path, fingerprint) if partial_path else []
    usage = metadata_usage
    for index, base_prompt in enumerate(request.user_prompts, start=1):
        if index <= len(sections):
            print(f"Resuming chunk {index}/{len(request.user_prompts)}…", file=sys.stderr)
            continue
        prompt = with_continuity_context(base_prompt, sections[-1]) if sections else base_prompt
        print(f"Processing chunk {index}/{len(request.user_prompts)}…", file=sys.stderr)
        result = _as_completion_result(request_completion_with_retry(api_key, model, request.system_prompt, prompt, endpoint=endpoint, timeout=args.timeout))
        sections.append(result.content)
        for key in usage:
            usage[key] += int(result.usage.get(key, 0) or 0)
        if partial_path:
            save_partial_sections(partial_path, fingerprint, sections)
    extras = parse_meta_arguments(args.meta)
    for key in ("description", "tags"):
        if key in metadata and key not in extras:
            extras[key] = metadata[key]
    if args.style == "flashcards" and output_path and output_path.suffix.lower() == ".csv":
        cards = extract_flashcards("\n\n".join(sections))
        if not cards:
            raise ValueError("The model did not return parseable Q:/A: flashcards; no CSV was written")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerows(cards)
        content = ""
    else:
        content = convert_transcript_to_blog(sections, request.title, request.author, pub_date, not args.no_frontmatter, extras)
    if partial_path:
        partial_path.unlink(missing_ok=True)
    return content, output_path, usage


def _is_youtube_url(value: str) -> bool:
    host = urllib.parse.urlparse(value).netloc.lower()
    return host.endswith("youtube.com") or host == "youtu.be"


def download_youtube_transcript(url: str) -> str:
    if not shutil.which("yt-dlp"):
        raise ValueError("YouTube input requires optional yt-dlp. Install it, then retry.")
    with tempfile.TemporaryDirectory(prefix="talk-to-blog-") as tempdir:
        template = str(Path(tempdir) / "transcript.%(ext)s")
        subprocess.run(["yt-dlp", "--write-auto-sub", "--write-sub", "--sub-langs", "en.*", "--sub-format", "vtt", "--skip-download", "--output", template, url], check=True, capture_output=True, text=True)
        files = list(Path(tempdir).glob("*.vtt"))
        if not files:
            raise ValueError("No English VTT subtitles were available for this YouTube video")
        return files[0].read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert talks into Markdown learning artifacts")
    parser.add_argument("transcript", help="Transcript file, directory, YouTube URL, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Output path, output directory for batch, or '-' for stdout")
    parser.add_argument("-f", "--format", choices=["txt", "srt", "vtt"], help="Transcript format; inferred from extension")
    parser.add_argument("-m", "--model", help="OpenAI-compatible model identifier")
    parser.add_argument("-e", "--endpoint", help="OpenAI-compatible chat-completions endpoint")
    parser.add_argument("--timeout", type=positive_int, default=OPENROUTER_TIMEOUT_SECONDS, help="API timeout seconds")
    parser.add_argument("-c", "--chunk-size", type=positive_int, default=500)
    parser.add_argument("-s", "--style", choices=sorted(STYLE_PROMPTS), default="blog")
    parser.add_argument("-p", "--prompt-file", help="File whose content replaces the selected style prompt")
    parser.add_argument("-k", "--keep-speakers", action="store_true")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Print prepared prompts without API calls")
    parser.add_argument("-t", "--title")
    parser.add_argument("-a", "--author")
    parser.add_argument("-d", "--date")
    parser.add_argument("--meta", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--no-frontmatter", action="store_true")
    try:
        installed_version = version("talk-to-blog")
    except PackageNotFoundError:
        installed_version = "0.2.0"
    parser.add_argument("--version", action="version", version=f"talk-to-blog {installed_version}")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if _is_youtube_url(args.transcript):
        paths: List[Optional[Path]] = [Path("youtube.vtt")]
        source_texts = [(download_youtube_transcript(args.transcript), Path("youtube.vtt"))]
    elif args.transcript == "-":
        paths = [None]
        source_texts = [(sys.stdin.read(), None)]
    else:
        source = Path(args.transcript).expanduser()
        if source.is_dir():
            paths = sorted(path for path in source.iterdir() if path.suffix.lower() in {".txt", ".srt", ".vtt"})
            if not paths:
                print(f"Error: No transcript files found in '{source}'", file=sys.stderr); sys.exit(1)
            source_texts = [(path.read_text(encoding="utf-8"), path) for path in paths]
        elif source.exists():
            source = source.resolve(); paths = [source]; source_texts = [(source.read_text(encoding="utf-8"), source)]
        else:
            print(f"Error: File '{source}' not found", file=sys.stderr); sys.exit(1)
    failures = 0
    for text, path in source_texts:
        env_vars = load_env(((path.parent / ".env") if path else Path.cwd() / ".env", Path.cwd() / ".env"))
        if len(source_texts) > 1 and args.output and args.output != "-":
            original_output, args.output = args.output, str(Path(args.output) / (path.stem + ".md"))
        else:
            original_output = None
        try:
            content, output_path, usage = convert_one(text, path, args, env_vars)
            if not args.dry_run and output_path is None:
                print(content)
            elif not args.dry_run and content:
                output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(content, encoding="utf-8")
            if not args.dry_run and output_path:
                print(f"Written to {output_path}", file=sys.stderr)
            if usage:
                print(f"Usage: {usage['prompt_tokens']} prompt tokens, {usage['completion_tokens']} completion tokens", file=sys.stderr)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            failures += 1; print(f"Error converting {path or args.transcript}: {error}", file=sys.stderr)
        finally:
            if original_output is not None:
                args.output = original_output
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
