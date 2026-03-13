# youtube-to-obsidian

[中文说明](./README.md)

Send YouTube videos or playlists into NotebookLM, generate structured Chinese notes, and write the results into Obsidian.

## Highlights

- Zero API cost: no OpenAI / Anthropic API key required, and no separate per-token model API bill
- Built for Obsidian: outputs structured Markdown meant for long-term knowledge capture
- Playlist aggregation: supports both per-video notes and one-note aggregate playlist analysis
- Transcript fallback: if NotebookLM cannot read a URL directly, the pipeline tries subtitles as a fallback

## What It Does

This project implements a full knowledge pipeline:

1. Read YouTube metadata with `yt-dlp`
2. Prefer sending the YouTube URL directly to NotebookLM
3. Fall back to transcript extraction if NotebookLM cannot read the URL
4. Run a prompt set to generate structured Chinese analysis
5. Write the result as Markdown into an Obsidian vault

The output is meant for long-term knowledge capture and retrieval, not just lightweight summarization.

## Current Features

- Process a single YouTube video
- Process a YouTube playlist
- Two playlist modes:
  - `individual`: analyze each video separately and write one note per video
  - `combined`: add multiple videos into one Notebook and generate one aggregate note
- Multi-prompt analysis:
  - `core` / `core_playlist`
  - `type_*`
  - `concepts`
  - `actions`
- Optional NotebookLM artifacts:
  - mind map
  - study guide
  - quiz
  - audio overview
- Automatic Obsidian frontmatter generation
- SQLite-based deduplication

## Tech Stack

- Python 3.12
- `uv`
- `yt-dlp`
- `notebooklm-py[browser]`
- `click`
- `pyyaml`
- `pytest`

## Project Layout

```text
youtube-to-obsidian/
├── main.py                 # CLI entrypoint
├── config.yaml             # Runtime config
├── prompts/                # All analysis prompts
├── src/
│   ├── extractor.py        # yt-dlp metadata/transcript extraction
│   ├── analyzer.py         # NotebookLM analysis
│   ├── generator.py        # Markdown generation
│   └── pipeline.py         # Workflow orchestration
├── tests/                  # Regression tests
└── processed.db            # Processing records (created at runtime)
```

## Requirements

You need:

- Python 3.12+
- `uv`
- `yt-dlp`
- A working Google / NotebookLM login
- A writable Obsidian vault

## Installation

### 1. Install dependencies

```bash
uv sync
```

Make sure `yt-dlp` is available in your PATH:

```bash
yt-dlp --version
```

### 2. Log in to NotebookLM

Before first use:

```bash
uv run notebooklm login
```

This opens a browser login flow. The CLI uses the saved local session afterward.

### 3. Update configuration

Edit [`config.yaml`](/Users/hongling/youtube-to-obsidian/config.yaml):

```yaml
obsidian:
  vault_path: "/Users/yourname/your-vault"
  inbox_folder: "0-收集箱"

youtube:
  preferred_languages: ["zh", "en"]

notebooklm:
  cleanup_notebook: true
  generate_audio: false
  generate_mind_map: true
  generate_quiz: false
  generate_study_guide: true
  analyze_concepts: true
  analyze_actions: true
  analyze_type_specific: true

playlist:
  default_delay: 5

db_path: "./processed.db"
```

The most important keys are:

- `obsidian.vault_path`
- `youtube.preferred_languages`
- `notebooklm.*`

## Usage

### Process a single video

```bash
uv run python main.py process "https://www.youtube.com/watch?v=VIDEO_ID"
```

Force reprocessing:

```bash
uv run python main.py process --force "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Process a playlist

#### Mode 1: individual

Each video gets its own Notebook and note.

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual
```

Only process the latest 5 videos:

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual --last 5
```

Set delay between videos:

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual --delay 10
```

#### Mode 2: combined

Add multiple videos as sources in one Notebook and generate one aggregate note.

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined
```

Only aggregate the last 7 videos:

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 7
```

Force rerun:

```bash
uv run python main.py playlist --force "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 7
```

## Output

### Single-video note

Default output path:

```text
{vault_path}/{inbox_folder}/video-title.md
```

The note includes:

- frontmatter
- core analysis
- type-specific analysis
- concept cards
- action items
- optional artifact links

### Playlist aggregate note

Default output path:

```text
{vault_path}/{inbox_folder}/playlist-title.md
```

The note includes:

- playlist frontmatter
- video list table
- `core_playlist` aggregate analysis
- type-specific analysis
- concept extraction
- action recommendations

### Artifact output

If enabled in config, artifacts are written into the vault:

- `mind_map` → `_附件/mindmaps/`
- `study_guide` → `_附件/`
- `quiz` → `_附件/quizzes/`
- `audio` → `_附件/`

## Prompt System

Prompt files live under `prompts/`:

- `core.txt`: core analysis for a single video
- `core_playlist.txt`: aggregate analysis for a playlist
- `type_tech_tutorial.txt`
- `type_knowledge.txt`
- `type_podcast.txt`
- `type_business.txt`
- `concepts.txt`
- `actions.txt`

Design rules:

- `core*` handles the main line of analysis
- `type_*` only adds supplemental analysis
- `concepts` only extracts concept cards
- `actions` only extracts actionable steps

## How It Works

### Single-video flow

1. Extract metadata with `yt-dlp`
2. Create a NotebookLM notebook
3. Try adding the YouTube URL directly
4. Fall back to transcript upload if needed
5. Run `core`
6. Run `type_* / concepts / actions`
7. Optionally generate artifacts
8. Write to Obsidian

### Playlist combined flow

1. Fetch playlist entries with `yt-dlp --flat-playlist`
2. Add multiple videos into one Notebook
3. Run `core_playlist`
4. Detect `content_type` and run the matching `type_*` prompt
5. Run `concepts` and `actions`
6. Generate one aggregate Markdown note

## Known Limitations

- `combined` mode is limited by NotebookLM source limits and currently supports up to 50 videos
- `combined` mode is usually much slower than single-video analysis
- If NotebookLM cannot read a YouTube URL directly, the project falls back to transcripts, but this does not guarantee success for every video
- Playlist output quality depends heavily on how well NotebookLM reads multiple sources together
- Videos without subtitles, or with poor subtitles, produce weaker analysis

## Debugging

### Run tests

```bash
pytest -q
```

### Common issues

#### 1. `yt-dlp` fails

Validate it manually:

```bash
yt-dlp --dump-json --no-download --no-playlist "https://www.youtube.com/watch?v=VIDEO_ID"
```

#### 2. NotebookLM stalls during analysis

First verify your login session:

```bash
uv run notebooklm login
```

Then reduce the workload, for example:

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 2
```

#### 3. Playlist output feels like a single-video note instead of a real aggregate

Make sure you are using:

```bash
--mode combined
```

The current implementation uses `core_playlist.txt` specifically to enforce aggregate analysis across multiple videos.

#### 4. Obsidian links or output paths look wrong

Check:

- `vault_path`
- that the vault directories exist
- that Obsidian is resolving standard wikilinks as expected

## Development

### Install dev dependencies

```bash
uv sync --dev
```

### Run tests

```bash
pytest -q
```

### Key files

- [`main.py`](/Users/hongling/youtube-to-obsidian/main.py)
- [`src/extractor.py`](/Users/hongling/youtube-to-obsidian/src/extractor.py)
- [`src/analyzer.py`](/Users/hongling/youtube-to-obsidian/src/analyzer.py)
- [`src/pipeline.py`](/Users/hongling/youtube-to-obsidian/src/pipeline.py)
- [`src/generator.py`](/Users/hongling/youtube-to-obsidian/src/generator.py)
- [`config.yaml`](/Users/hongling/youtube-to-obsidian/config.yaml)

## License

Not specified.
