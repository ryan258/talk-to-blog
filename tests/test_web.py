"""Smoke tests for the local web UI."""
import unittest
from unittest.mock import MagicMock

from talk_to_blog.web import Handler, detect_format, page_form, page_result, run_conversion


class TestDetectFormat(unittest.TestCase):
    def test_vtt(self):
        self.assertEqual(detect_format("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi"), "vtt")

    def test_vtt_with_byte_order_mark(self):
        self.assertEqual(detect_format("\ufeffWEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi"), "vtt")

    def test_srt(self):
        self.assertEqual(detect_format("1\n00:00:01,000 --> 00:00:02,000\nhi"), "srt")

    def test_plain(self):
        self.assertEqual(detect_format("Just a talk about things."), "txt")


class TestPages(unittest.TestCase):
    def test_form_lists_all_styles(self):
        page = page_form()
        for style in ("blog", "notes", "summary", "actions", "flashcards", "eli5"):
            self.assertIn(f"value='{style}'", page)

    def test_form_escapes_error_and_transcript(self):
        page = page_form(error="<b>boom</b>", transcript="<script>x</script>")
        self.assertNotIn("<b>boom</b>", page)
        self.assertNotIn("<script>x</script>", page)

    def test_form_preserves_optional_fields_after_an_error(self):
        page = page_form(
            error="Conversion failed",
            transcript="A transcript",
            style="notes",
            title="My Title",
            author="Jane",
            model="local-model",
            keep_speakers=True,
        )
        self.assertIn("value='My Title'", page)
        self.assertIn("value='Jane'", page)
        self.assertIn("value='local-model'", page)
        self.assertIn("name='keep_speakers' checked", page)

    def test_result_escapes_markdown(self):
        page = page_result("# Hi <script>alert(1)</script>", "My <Title>", "notes")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("My &lt;Title&gt;", page)

    def test_send_ignores_disconnects_after_headers(self):
        class DisconnectingWriter:
            def write(self, payload):
                raise BrokenPipeError

        handler = object.__new__(Handler)
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = DisconnectingWriter()

        Handler._send(handler, "page")
        handler.end_headers.assert_called_once()


class TestRunConversionValidation(unittest.TestCase):
    def test_empty_transcript_rejected(self):
        with self.assertRaises(ValueError):
            run_conversion({})

    def test_unknown_style_rejected(self):
        with self.assertRaises(ValueError):
            run_conversion({"transcript": ["hello"], "style": ["haiku"]})


if __name__ == "__main__":
    unittest.main()
