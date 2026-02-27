# The Picture of Dorian Gray — Test Corpus

This directory contains the text of *The Picture of Dorian Gray* by **Oscar Wilde** (1890), used as a real-world test corpus for lit-critic development and integration testing.

## Source

- **Project Gutenberg:** <https://www.gutenberg.org/files/174/174-h/174-h.htm>
- **License:** Public domain

## Contents

The novel text is split into chapter files (one file per chapter). Index files prepared for lit-critic are included alongside:

| File | Description |
|------|-------------|
| `chapter-*.txt` | Chapter text (no @@META headers) |
| `CAST.md` | Character facts and relationships |
| `THREADS.md` | Narrative threads |
| `TIMELINE.md` | Chapter sequence and summaries |

## Setup

If you've cloned the repo and this directory is empty (no chapter files), you need to populate it:

1. Download the plain-text version from Project Gutenberg
2. Split into chapter files named `chapter-01.txt` through `chapter-20.txt` (plus the Preface)
3. Place your `CAST.md`, `THREADS.md`, and `TIMELINE.md` here

The chapter files and index files should all live flat in this directory — no subdirectories needed.

## Usage in Tests

Tests can access this directory via the `real_novel_dir` pytest fixture:

```python
def test_something_with_real_text(real_novel_dir):
    # real_novel_dir is a Path to this directory
    # Skips automatically if no chapter files are present
    ...
```

## Note

This text is in the public domain and is redistributable. The index files (CAST.md, THREADS.md, TIMELINE.md) were prepared specifically for this project.
