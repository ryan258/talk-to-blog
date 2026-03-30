#!/usr/bin/env python3
"""Tests for the converter module."""
import unittest
from talk_to_blog.converter import (
    parse_srt,
    parse_vtt,
    clean_transcript,
    chunk_text,
    generate_frontmatter,
    convert_transcript_to_blog,
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
        # Should skip the first block since no timestamp, but still parse second
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
        # Should skip the first block since timestamp is malformed (no '-->')
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


class TestChunkText(unittest.TestCase):
    def test_small_text(self):
        text = "This is a test."
        chunks = chunk_text(text, chunk_size=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "This is a test.")

    def test_large_text(self):
        # Create text with 100 words
        words = ["word"] * 100
        text = ". ".join(words) + "."
        chunks = chunk_text(text, chunk_size=30)
        self.assertEqual(len(chunks), 4)  # 100/30 ≈ 3.33, so 4 chunks
        for chunk in chunks:
            self.assertLessEqual(len(chunk.split()), 35)  # Allow some flexibility


class TestGenerateFrontmatter(unittest.TestCase):
    def test_frontmatter_format(self):
        result = generate_frontmatter("My Title", "John Doe", "2024-01-01")
        self.assertIn("title: \"My Title\"", result)
        self.assertIn("author: \"John Doe\"", result)
        self.assertIn("date: \"2024-01-01\"", result)
        self.assertTrue(result.startswith("---"))
        self.assertTrue(result.endswith("---\n\n"))


class TestConvertTranscriptToBlog(unittest.TestCase):
    def test_basic_conversion(self):
        transcript = "Hello world. This is a test."
        result = convert_transcript_to_blog(transcript, include_frontmatter=False)
        self.assertIn("# Conference Talk", result)
        self.assertIn("Hello world. This is a test.", result)
        self.assertIn("## Part 1", result)

    def test_with_frontmatter(self):
        transcript = "Hello world."
        result = convert_transcript_to_blog(transcript, title="My Talk", author="Jane Doe")
        self.assertIn("title: \"My Talk\"", result)
        self.assertIn("author: \"Jane Doe\"", result)
        self.assertIn("# My Talk", result)

    def test_srt_input(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
Hello world.
"""
        result = convert_transcript_to_blog(srt, transcript_format="srt")
        self.assertIn("Hello world.", result)


if __name__ == "__main__":
    unittest.main()