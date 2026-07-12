# Happy path: YouTube talk → learning artifact

Goal: grab the transcript YouTube already has, paste it, get a Markdown file.
Nothing to install beyond the tool itself.

## One-time setup

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

## The flow

1. On the video page, click **"...more"** in the description → **Show transcript**.
2. Select the whole transcript panel and copy it. The `0:00`-style timestamp
   lines come along for the ride — that's fine, they're stripped automatically.
3. Paste it in:

```bash
# From the clipboard, straight through (macOS)
pbpaste | talk-to-blog -

# Or use the web UI and paste into the big box
talk-to-blog-web
```

What happens next:

1. Timestamp lines, filler words, and speaker labels are cleaned out.
2. A title, description, and tags are generated for you (skip with `-t "My Title"`).
3. Each chunk is converted with continuity context; progress prints per chunk.
4. Output lands in `./output/YYYYMMDD-generated-title.md` with frontmatter
   (use `-o -` to print to stdout instead, or `-o path.md` to pick the file).

## Variations

```bash
# Study notes instead of a blog post
pbpaste | talk-to-blog - -s notes

# Flashcards straight to an Anki-importable CSV
pbpaste | talk-to-blog - -s flashcards -o deck.csv

# Panel or interview — keep who said what
pbpaste | talk-to-blog - -k
```

## Alternative: let yt-dlp fetch the captions

If you'd rather hand over the URL (batch runs, no browser open):

```bash
brew install yt-dlp     # one-time
talk-to-blog "https://www.youtube.com/watch?v=VIDEO_ID"
```

Same pipeline, but output defaults to `./output/YYYYMMDD-generated-title.md`,
and interrupted runs resume from `*.partial.json` on rerun.

## If it goes wrong

| Symptom | Fix |
|---------|-----|
| No "Show transcript" option on the video | The video has no captions — try the yt-dlp route or another recording |
| `OPENROUTER_API_KEY not found` | Put the key in `.env` in the directory you run from |
| Output still contains stray timestamps | Update: timestamp stripping landed 2026-07-11; check `talk-to-blog --version` |
| `YouTube input requires optional yt-dlp` | Only the URL route needs it: `brew install yt-dlp` |
