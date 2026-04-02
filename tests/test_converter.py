#!/usr/bin/env python3
"""Tests for the converter and CLI modules."""
import argparse
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from talk_to_blog.cli import (
    extract_openrouter_content,
    load_env,
    main,
    positive_int,
    request_openrouter_completion,
)
from talk_to_blog.converter import (
    chunk_text,
    clean_transcript,
    convert_transcript_to_blog,
    generate_frontmatter,
    parse_srt,
    parse_vtt,
    prepare_conversion_request,
)


class TestParseSRT(unittest.TestCase):
    def test_basic_srt(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
Hello world.

2
00:00:02,000 --> 00:00:04,000
This is a test.
"""
        result = parse_srt(srt)
        self.assertEqual(result, "Hello world. This is a test.")

    def test_srt_with_multiline_text(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
Hello world.
This is line two.

2
00:00:02,000 --> 00:00:04,000
This is a test.
"""
        result = parse_srt(srt)
        self.assertEqual(result, "Hello world. This is line two. This is a test.")

    def test_srt_missing_timestamp(self):
        srt = """1
Hello world.

2
00:00:02,000 --> 00:00:04,000
This is a test.
"""
        result = parse_srt(srt)
        self.assertEqual(result, "This is a test.")

    def test_srt_malformed_timestamp(self):
        srt = """1
00:00:00,000 - 00:00:02,000
Hello world.

2
00:00:02,000 --> 00:00:04,000
This is a test.
"""
        result = parse_srt(srt)
        self.assertEqual(result, "This is a test.")

    def test_srt_empty_input(self):
        result = parse_srt("")
        self.assertEqual(result, "")

    def test_srt_no_text(self):
        srt = """1
00:00:00,000 --> 00:00:02,000

2
00:00:02,000 --> 00:00:04,000
"""
        result = parse_srt(srt)
        self.assertEqual(result, "")


class TestParseVTT(unittest.TestCase):
    def test_basic_vtt(self):
        vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
Hello world.

00:00:02.000 --> 00:00:04.000
This is a test.
"""
        result = parse_vtt(vtt)
        self.assertEqual(result, "Hello world. This is a test.")


class TestCleanTranscript(unittest.TestCase):
    def test_remove_speaker_labels(self):
        text = "John: Hello there. Mary: Hi!"
        result = clean_transcript(text)
        self.assertEqual(result, "Hello there. Hi!")

    def test_remove_fillers(self):
        text = "Um, so like, you know, this is basically a test."
        result = clean_transcript(text)
        self.assertEqual(result, "this is a test.")

    def test_keep_legitimate_like(self):
        text = "I like Python."
        result = clean_transcript(text)
        self.assertEqual(result, "I like Python.")

    def test_keep_non_speaker_label_content(self):
        text = "Note: this is important."
        result = clean_transcript(text)
        self.assertEqual(result, "Note: this is important.")

    def test_keep_capitalized_prose_label(self):
        text = "The API: returns JSON."
        result = clean_transcript(text)
        self.assertEqual(result, "The API: returns JSON.")

    def test_remove_speaker_label_with_lowercase_speech(self):
        text = "Speaker 1: hello there."
        result = clean_transcript(text)
        self.assertEqual(result, "hello there.")

    def test_remove_lowercase_speaker_label(self):
        text = "speaker1: hello there."
        result = clean_transcript(text)
        self.assertEqual(result, "hello there.")

    def test_keep_non_filler_so(self):
        text = "Please do so. Next sentence."
        result = clean_transcript(text)
        self.assertEqual(result, "Please do so. Next sentence.")


class TestChunkText(unittest.TestCase):
    def test_small_text(self):
        text = "This is a test."
        chunks = chunk_text(text, chunk_size=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "This is a test.")

    def test_large_text(self):
        words = ["word"] * 100
        text = ". ".join(words) + "."
        chunks = chunk_text(text, chunk_size=30)
        self.assertEqual(len(chunks), 4)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.split()), 35)

    def test_invalid_chunk_size(self):
        with self.assertRaisesRegex(ValueError, "chunk_size must be positive"):
            chunk_text("This is a test.", chunk_size=0)


class TestGenerateFrontmatter(unittest.TestCase):
    def test_frontmatter_format(self):
        result = generate_frontmatter("My Title", "John Doe", "2024-01-01")
        self.assertIn('title: "My Title"', result)
        self.assertIn('author: "John Doe"', result)
        self.assertIn('date: "2024-01-01"', result)
        self.assertTrue(result.startswith("---"))
        self.assertTrue(result.endswith("---\n\n"))

    def test_frontmatter_escapes_quotes(self):
        result = generate_frontmatter('My "Awesome" Talk', "John Doe", "2024-01-01")
        self.assertIn('title: "My \\"Awesome\\" Talk"', result)

    def test_frontmatter_blank_date_when_not_provided(self):
        result = convert_transcript_to_blog("Body", title="My Talk", author="Jane Doe")
        self.assertIn('date: ""', result)


class TestConversionPlanning(unittest.TestCase):
    def test_prepare_conversion_request_uses_chunk_size(self):
        words = ["word"] * 100
        transcript = ". ".join(words) + "."
        request = prepare_conversion_request(transcript, chunk_size=30)
        self.assertEqual(len(request.user_prompts), 4)
        self.assertIn("Chunk: 1/4", request.user_prompts[0])
        self.assertIn("Chunk: 4/4", request.user_prompts[-1])

    def test_prepare_conversion_request_parses_srt(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
Hello world.
"""
        request = prepare_conversion_request(srt, transcript_format="srt")
        self.assertIn("Transcript:\nHello world.", request.user_prompts[0])


class TestConvertTranscriptToBlog(unittest.TestCase):
    def test_basic_conversion(self):
        result = convert_transcript_to_blog(
            "This is a mock AI generated post.",
            title="Conference Talk",
            include_frontmatter=False,
        )
        self.assertIn("# Conference Talk", result)
        self.assertIn("This is a mock AI generated post.", result)

    def test_with_frontmatter(self):
        result = convert_transcript_to_blog(
            "This is a mock AI generated post.",
            title="My Talk",
            author="Jane Doe",
            date="2024-01-01",
        )
        self.assertIn('title: "My Talk"', result)
        self.assertIn('author: "Jane Doe"', result)
        self.assertIn("# My Talk", result)

    def test_multiple_sections(self):
        result = convert_transcript_to_blog(
            ["## Intro\n\nPart one.", "## Outro\n\nPart two."],
            title="My Talk",
            include_frontmatter=False,
        )
        self.assertIn("## Intro", result)
        self.assertIn("## Outro", result)


class TestCliHelpers(unittest.TestCase):
    def test_positive_int(self):
        self.assertEqual(positive_int("5"), 5)

    def test_positive_int_rejects_zero(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "chunk size must be a positive integer"):
            positive_int("0")

    def test_load_env_uses_real_environment_as_fallback(self):
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = Path(tempdir) / ".env"
            env_path.write_text("OPENROUTER_API_KEY=from-dotenv\n", encoding="utf-8")
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "from-env"}, clear=False):
                env_vars = load_env((env_path,))
        self.assertEqual(env_vars["OPENROUTER_API_KEY"], "from-dotenv")

    def test_load_env_reads_real_environment_when_dotenv_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            env_vars = {}
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "from-env"}, clear=False):
                env_vars = load_env((Path(tempdir) / ".env",))
        self.assertEqual(env_vars["OPENROUTER_API_KEY"], "from-env")

    def test_load_env_reads_first_available_env_file(self):
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as cwd_dir:
            project_env = Path(project_dir) / ".env"
            cwd_env = Path(cwd_dir) / ".env"
            project_env.write_text("OPENROUTER_API_KEY=from-project\n", encoding="utf-8")
            cwd_env.write_text("OPENROUTER_API_KEY=from-cwd\n", encoding="utf-8")
            env_vars = load_env((project_env, cwd_env))
        self.assertEqual(env_vars["OPENROUTER_API_KEY"], "from-project")

    def test_extract_openrouter_content(self):
        payload = {
            "choices": [{"message": {"content": "This is a mock AI generated post."}}],
        }
        self.assertEqual(
            extract_openrouter_content(payload),
            "This is a mock AI generated post.",
        )

    def test_extract_openrouter_content_rejects_error_payload(self):
        payload = {"error": {"message": "rate limited"}}
        with self.assertRaisesRegex(ValueError, "rate limited"):
            extract_openrouter_content(payload)

    @patch("urllib.request.urlopen")
    def test_request_openrouter_completion(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "Generated markdown"}}]}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        content = request_openrouter_completion(
            api_key="dummy",
            ai_model="test-model",
            system_prompt="system prompt",
            user_prompt="user prompt",
        )

        self.assertEqual(content, "Generated markdown")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 60)

    @patch("urllib.request.urlopen")
    def test_request_openrouter_completion_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://openrouter.ai/api/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(json.dumps({"error": {"message": "rate limited"}}).encode("utf-8")),
        )

        with self.assertRaisesRegex(ValueError, "OpenRouter request failed \\(429\\): rate limited"):
            request_openrouter_completion(
                api_key="dummy",
                ai_model="test-model",
                system_prompt="system prompt",
                user_prompt="user prompt",
            )


class TestMain(unittest.TestCase):
    @patch("talk_to_blog.cli.request_openrouter_completion", return_value="Generated markdown")
    def test_main_reads_env_next_to_transcript(self, mock_request):
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as run_dir:
            project_path = Path(project_dir)
            transcript_path = project_path / "talk.txt"
            transcript_path.write_text("Hello world.", encoding="utf-8")
            (project_path / ".env").write_text(
                "OPENROUTER_API_KEY=from-project\nOPENROUTER_MODEL=model-from-env\n",
                encoding="utf-8",
            )

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            with patch("talk_to_blog.cli.Path.cwd", return_value=Path(run_dir)):
                with patch("sys.argv", ["talk-to-blog", str(transcript_path), "-o", "-"]):
                    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                        main()

        self.assertIn("# Conference Talk", stdout_buffer.getvalue())
        self.assertEqual(stderr_buffer.getvalue(), "")
        self.assertEqual(mock_request.call_args.kwargs["api_key"], "from-project")
        self.assertEqual(mock_request.call_args.kwargs["ai_model"], "model-from-env")

    @patch("talk_to_blog.cli.request_openrouter_completion", return_value="Generated markdown")
    def test_main_writes_default_output_file(self, mock_request):
        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            transcript_path = project_path / "talk.txt"
            transcript_path.write_text("Hello world.", encoding="utf-8")
            (project_path / ".env").write_text("OPENROUTER_API_KEY=from-project\n", encoding="utf-8")

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "talk-to-blog",
                    str(transcript_path),
                    "-t",
                    "My Great Talk",
                    "-d",
                    "2026-04-02",
                ],
            ):
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    main()

            output_path = project_path / "output" / "20260402-my-great-talk.md"
            self.assertEqual(stdout_buffer.getvalue(), "")
            self.assertTrue(output_path.exists())
            self.assertIn("# My Great Talk", output_path.read_text(encoding="utf-8"))
            self.assertIn(str(output_path), stderr_buffer.getvalue())
            self.assertEqual(mock_request.call_args.kwargs["api_key"], "from-project")

    def test_main_rejects_invalid_chunk_size(self):
        with tempfile.TemporaryDirectory() as project_dir:
            transcript_path = Path(project_dir) / "talk.txt"
            transcript_path.write_text("Hello world.", encoding="utf-8")
            stderr_buffer = io.StringIO()
            with self.assertRaises(SystemExit) as exc_info:
                with patch("sys.argv", ["talk-to-blog", str(transcript_path), "--chunk-size", "0"]):
                    with redirect_stderr(stderr_buffer):
                        main()
        self.assertEqual(exc_info.exception.code, 2)
        self.assertIn("chunk size must be a positive integer", stderr_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
