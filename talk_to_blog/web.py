#!/usr/bin/env python3
"""Local web UI: paste a transcript or YouTube link, get a learning artifact.

Run with `talk-to-blog-web` or `python -m talk_to_blog.web [port]`.
Stdlib only; binds to 127.0.0.1 and reuses the CLI's env/API plumbing.
"""
import html
import re
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .cli import (
    DEFAULT_OPENROUTER_MODEL,
    METADATA_SYSTEM_PROMPT,
    OPENROUTER_URL,
    RequestError,
    _is_youtube_url,
    _slugify_title,
    download_youtube_transcript,
    load_env,
    parse_metadata_response,
    request_completion_with_retry,
)
from .converter import (
    STYLE_PROMPTS,
    convert_transcript_to_blog,
    prepare_conversion_request,
    with_continuity_context,
)

DEFAULT_PORT = 8765

STYLE_BLURBS = {
    "blog": ("Blog post", "A polished post, ready to publish"),
    "notes": ("Study notes", "Key concepts, definitions, examples"),
    "summary": ("Summary", "TL;DR and key takeaways"),
    "actions": ("Action plan", "A checklist of next steps"),
    "flashcards": ("Flashcards", "Q&A pairs for spaced review"),
    "eli5": ("Explain simply", "Plain language, no jargon"),
}

_SRT_CUE_RE = re.compile(r"^\d+\s*\n\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->", re.MULTILINE)

CSS = """
:root {
  --paper: #EFF2F5; --card: #FFFFFF; --ink: #1B2733; --slate: #5B6B7A;
  --line: #D6DDE3; --mark: #FFDE59; --mark-soft: #FFF6CC;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 44rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
h1, h2 {
  font-family: "Iowan Old Style", Charter, Georgia, serif;
  font-weight: 600; letter-spacing: -0.01em; margin: 0;
}
h1 { font-size: 2rem; }
.tagline { color: var(--slate); margin: 0.35rem 0 2rem; }
.eyebrow {
  font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--slate); margin: 0 0 0.5rem;
}
label.field { display: block; font-weight: 600; margin: 1.5rem 0 0.4rem; }
textarea, input[type="text"] {
  width: 100%; border: 1px solid var(--line); border-radius: 6px;
  background: var(--card); color: var(--ink); padding: 0.6rem 0.7rem; font-size: 0.95rem;
}
textarea {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.85rem; min-height: 14rem; resize: vertical;
}
textarea:focus-visible, input:focus-visible, button:focus-visible,
.style-card input:focus-visible + span {
  outline: 3px solid var(--mark); outline-offset: 1px;
}
.hint { color: var(--slate); font-size: 0.85rem; margin: 0.35rem 0 0; }
.styles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.6rem; }
@media (max-width: 560px) { .styles { grid-template-columns: 1fr 1fr; } }
.style-card { display: block; cursor: pointer; }
.style-card input { position: absolute; opacity: 0; }
.style-card span {
  display: block; height: 100%; background: var(--card); border: 1px solid var(--line);
  border-left: 5px solid var(--line); border-radius: 6px; padding: 0.55rem 0.7rem;
}
.style-card b {
  display: block; font-family: "Iowan Old Style", Charter, Georgia, serif;
  font-size: 1rem; font-weight: 600;
}
.style-card small { color: var(--slate); font-size: 0.78rem; line-height: 1.35; }
.style-card input:checked + span {
  border-left-color: var(--mark); background: var(--mark-soft);
}
details { margin-top: 1.5rem; }
summary { cursor: pointer; font-weight: 600; color: var(--slate); }
.options { display: grid; grid-template-columns: 1fr 1fr; gap: 0 1rem; }
@media (max-width: 560px) { .options { grid-template-columns: 1fr; } }
.check { display: flex; gap: 0.5rem; align-items: center; margin-top: 1.5rem; font-weight: 600; }
button {
  margin-top: 2rem; border: 1px solid var(--ink); border-radius: 6px; cursor: pointer;
  background: var(--mark); color: var(--ink); font: 600 1rem system-ui, sans-serif;
  padding: 0.7rem 1.6rem;
}
button:disabled { opacity: 0.6; cursor: wait; }
button.quiet { background: var(--card); border-color: var(--line); margin-top: 0; padding: 0.45rem 1rem; font-size: 0.9rem; }
.error {
  background: var(--card); border-left: 5px solid #C0392B; border-radius: 6px;
  padding: 0.8rem 1rem; margin-bottom: 1.5rem;
}
.result-bar { display: flex; gap: 0.6rem; align-items: center; margin: 1.2rem 0 0.6rem; }
#output { min-height: 24rem; }
a { color: inherit; }
"""

FORM_JS = """
document.querySelector("form").addEventListener("submit", function () {
  var b = document.querySelector("button[type=submit]");
  b.disabled = true;
  b.textContent = "Converting\\u2026 long talks can take a few minutes";
});
"""

RESULT_JS = """
var out = document.getElementById("output");
document.getElementById("copy").addEventListener("click", function () {
  navigator.clipboard.writeText(out.value);
  this.textContent = "Copied";
});
document.getElementById("download").addEventListener("click", function () {
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([out.value], { type: "text/markdown" }));
  a.download = this.dataset.filename;
  a.click();
  URL.revokeObjectURL(a.href);
});
"""


def detect_format(text: str) -> str:
    """Infer txt/srt/vtt from pasted content so users never pick a format."""
    if text.lstrip("\ufeff \t\r\n")[:20].startswith("WEBVTT"):
        return "vtt"
    if _SRT_CUE_RE.search(text):
        return "srt"
    return "txt"


def _page(title: str, body: str, script: str = "") -> str:
    script_tag = f"<script>{script}</script>" if script else ""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body><main>{body}</main>{script_tag}</body></html>"
    )


def _style_cards(selected: str) -> str:
    cards = []
    for key, (name, blurb) in STYLE_BLURBS.items():
        checked = " checked" if key == selected else ""
        cards.append(
            f"<label class='style-card'><input type='radio' name='style' value='{key}'{checked}>"
            f"<span><b>{name}</b><small>{blurb}</small></span></label>"
        )
    return "".join(cards)


def page_form(
    error: str = "",
    transcript: str = "",
    style: str = "blog",
    title: str = "",
    author: str = "",
    model: str = "",
    keep_speakers: bool = False,
) -> str:
    error_html = f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    body = f"""
<p class='eyebrow'>talk-to-blog</p>
<h1>Turn a talk into something you'll keep</h1>
<p class='tagline'>Paste a transcript or a YouTube link, pick what you want out of it.</p>
{error_html}
<form method='post' action='/convert'>
  <label class='field' for='transcript'>Transcript or YouTube link</label>
  <textarea id='transcript' name='transcript' required
    placeholder='Paste the transcript text (plain, SRT, or VTT — detected automatically), or a YouTube URL'>{html.escape(transcript)}</textarea>
  <label class='field'>What should this become?</label>
  <div class='styles'>{_style_cards(style)}</div>
  <details>
    <summary>More options</summary>
    <div class='options'>
      <div><label class='field' for='title'>Title</label>
        <input type='text' id='title' name='title' value='{html.escape(title, quote=True)}'>
        <p class='hint'>Leave blank to have one written for you</p></div>
      <div><label class='field' for='author'>Author</label>
        <input type='text' id='author' name='author' value='{html.escape(author, quote=True)}'></div>
      <div><label class='field' for='model'>Model</label>
        <input type='text' id='model' name='model' value='{html.escape(model, quote=True)}' placeholder='{DEFAULT_OPENROUTER_MODEL}'></div>
    </div>
    <label class='check'><input type='checkbox' name='keep_speakers'{" checked" if keep_speakers else ""}>
      Keep speaker names <span class='hint'>(for panels and interviews)</span></label>
  </details>
  <button type='submit'>Convert</button>
</form>"""
    return _page("talk-to-blog", body, FORM_JS)


def page_result(markdown: str, title: str, style: str) -> str:
    filename = f"{_slugify_title(title)}.md"
    body = f"""
<p class='eyebrow'>Converted · {html.escape(STYLE_BLURBS[style][0])}</p>
<h1>{html.escape(title)}</h1>
<div class='result-bar'>
  <button class='quiet' id='copy'>Copy Markdown</button>
  <button class='quiet' id='download' data-filename='{html.escape(filename)}'>Download {html.escape(filename)}</button>
  <a href='/'>Convert another</a>
</div>
<textarea id='output' readonly aria-label='Converted Markdown'>{html.escape(markdown)}</textarea>"""
    return _page(f"{title} — talk-to-blog", body, RESULT_JS)


def run_conversion(form: dict) -> tuple:
    """Run the full pipeline for one web submission; returns (markdown, title, style)."""

    def field(name: str) -> str:
        return form.get(name, [""])[0].strip()

    source = field("transcript")
    if not source:
        raise ValueError("Paste a transcript or a YouTube link first.")
    style = field("style") or "blog"
    if style not in STYLE_PROMPTS:
        raise ValueError(f"Unknown style: {style}")
    title = field("title") or None
    author = field("author") or None
    keep_speakers = "keep_speakers" in form

    env = load_env()
    endpoint = env.get("OPENROUTER_BASE_URL") or env.get("OPENAI_BASE_URL") or OPENROUTER_URL
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key and urllib.parse.urlparse(endpoint).netloc == "openrouter.ai":
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to your environment or a .env file "
            "in the folder you launched from, then try again."
        )
    model = field("model") or env.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)

    if _is_youtube_url(source):
        source, transcript_format = download_youtube_transcript(source), "vtt"
    else:
        transcript_format = detect_format(source)

    pub_date = datetime.now().strftime("%Y-%m-%d")
    request = prepare_conversion_request(
        source, transcript_format, title, author, pub_date,
        style=style, keep_speakers=keep_speakers,
    )
    print(f"Web UI: Starting conversion. style={style}, model={model}, chunks={len(request.user_prompts)}", file=sys.stderr)
    if not title:
        try:
            print("Web UI: Auto-generating metadata (title, description, tags)...", file=sys.stderr)
            meta_result = request_completion_with_retry(
                api_key, model, METADATA_SYSTEM_PROMPT,
                request.cleaned_transcript[:6000], endpoint=endpoint,
            )
            generated = parse_metadata_response(meta_result.content).get("title")
            if generated:
                request = prepare_conversion_request(
                    source, transcript_format, generated, author, pub_date,
                    style=style, keep_speakers=keep_speakers,
                )
        except (RequestError, ValueError):
            pass  # fall back to the default title rather than failing the run

    sections = []
    for index, prompt in enumerate(request.user_prompts, start=1):
        prompt = with_continuity_context(prompt, "\n\n".join(sections)) if sections else prompt
        print(f"Web UI: Processing chunk {index}/{len(request.user_prompts)}...", file=sys.stderr)
        result = request_completion_with_retry(
            api_key, model, request.system_prompt, prompt, endpoint=endpoint
        )
        sections.append(result.content)
    print("Web UI: Conversion complete!", file=sys.stderr)
    markdown = convert_transcript_to_blog(sections, request.title, request.author, pub_date)
    return markdown, request.title, style


class Handler(BaseHTTPRequestHandler):
    def _send(self, page: str, status: int = 200) -> None:
        payload = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(page_form())
        else:
            self._send(_page("Not found", "<h1>Not found</h1><p><a href='/'>Back</a></p>"), 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        try:
            markdown, title, style = run_conversion(form)
            self._send(page_result(markdown, title, style))
        except Exception as error:  # surface any failure on the form, keep the paste
            transcript = form.get("transcript", [""])[0]
            style = form.get("style", ["blog"])[0]
            self._send(
                page_form(
                    str(error),
                    transcript,
                    style,
                    form.get("title", [""])[0],
                    form.get("author", [""])[0],
                    form.get("model", [""])[0],
                    "keep_speakers" in form,
                ),
                422,
            )

    def log_message(self, format: str, *args) -> None:
        pass  # ponytail: quiet server; conversion progress isn't surfaced per-chunk in the UI


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"talk-to-blog web UI at {url} (Ctrl+C to stop)")
    threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
