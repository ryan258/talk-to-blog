#!/usr/bin/env python3
"""Command-line interface for talk-to-blog converter."""
import argparse
import sys
from pathlib import Path
from .converter import convert_transcript_to_blog


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Convert conference talk transcripts into blog posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s transcript.txt -o blog.md
  %(prog)s transcript.srt --format srt -o blog.md
  %(prog)s transcript.vtt --format vtt -t "My Talk Title" -a "Jane Doe"
        """
    )
    parser.add_argument("transcript", help="Path to transcript file")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("-f", "--format", choices=["txt", "srt", "vtt"], default="txt",
                        help="Transcript format (default: txt)")
    parser.add_argument("-t", "--title", help="Blog post title (default: derived from filename)")
    parser.add_argument("-a", "--author", help="Author name (default: 'Speaker')")
    parser.add_argument("-d", "--date", help="Publication date (default: today)")
    parser.add_argument("--no-frontmatter", action="store_true",
                        help="Omit YAML frontmatter")
    parser.add_argument("--chunk-size", type=int, default=500,
                        help="Approximate words per section (default: 500)")
    
    args = parser.parse_args()
    
    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"Error: File '{transcript_path}' not found", file=sys.stderr)
        sys.exit(1)
    
    try:
        transcript_text = transcript_path.read_text(encoding="utf-8")
    except Exception as e:
        
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        blog_content = convert_transcript_to_blog(
            transcript_text,
            transcript_format=args.format,
            title=args.title,
            author=args.author,
            date=args.date,
            include_frontmatter=not args.no_frontmatter,
            chunk_size=args.chunk_size
        )
    except ValueError as e:
        
        print(f"Error converting transcript: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.output:
        try:
            Path(args.output).write_text(blog_content, encoding="utf-8")
            print(f"Blog post written to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(blog_content)


if __name__ == "__main__":
    main()