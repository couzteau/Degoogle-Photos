# AGENTS.md

Guidance for AI coding agents working in this repository.

**Read [CONTRIBUTING.md](CONTRIBUTING.md) first.** Its setup steps, code guidelines
(style, docstrings, testing, commits), project structure, and privacy philosophy apply
to agents as well. This file only adds agent-specific context — do not repeat
CONTRIBUTING.md content here, to keep the two from drifting apart.

## Project overview

Degoogle-Photos is a Python CLI that organizes Google Takeout photo exports into clean
`YYYY/MM/` folder hierarchies. It has two operating modes:

- **Takeout migration (default):** Scans multiple `Takeout*/Google Photos/` directories,
  builds a global index, extracts the best date per file (EXIF > JSON `photoTakenTime` >
  filename > JSON `creationTime` > file mtime), deduplicates by MD5 hash + date, copies
  media into `YYYY/MM/` folders (keeping JSON sidecars alongside), creates `Albums/`
  symlinks, and emits an HTML report.
- **Dedup mode (`--dedup-scan`):** Scans any folder(s) recursively, computes MD5 checksums,
  keeps one file per duplicate group (shortest path wins), copies unique files into a
  date-organised `YYYY/MM/` structure, and recreates the source folder tree under
  `by-folder/` as relative symlinks. The source folders are never modified.

The package is pure Python stdlib plus `Pillow`. Build/packaging is managed exclusively by
`pyproject.toml`. There is a thin `migrate_photos.py` wrapper that delegates to
`degoogle_photos.cli:main` for backwards compatibility.

## Repository layout

- `plans/` — implementation plans. Active plans live in `plans/NNNN-slug.md` (4-digit,
  zero-padded numbers, never reused or renumbered — check existing files to find the
  next number). Completed plans live in `plans/archive/`; move with `git mv` when done
  without editing the file — folder position is the status marker.

## Setup and verification

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

On Windows activate with `.venv\Scripts\activate` instead.

To run a single module or test:

```bash
pytest -v tests/test_dedup.py
pytest -v tests/test_dedup_mode.py -k import_name
```

## Test conventions

- Tests live in `tests/` and share fixtures from `tests/conftest.py`:
  - `fake_takeout` — builds a minimal Takeout tree (JPEG + JSON sidecar + dummy mp4 +
    `metadata.json`) for indexing/migration tests.
  - `output_dir` — a clean, empty output directory.
- `tests/test_dedup_mode.py` is the end-to-end integration suite for `--dedup-scan`.
- Keep new tests consistent with these fixtures and mirror the structure of existing test
  modules.

## Code organization

- `indexing.py` — Takeout directory scanning, JSON sidecar indexing, recursive media finder.
- `dates.py` — date extraction cascade (EXIF, JSON, filename, mtime).
- `metadata.py` — rich metadata extraction for report tooltips.
- `dedup.py` — MD5 hashing, dedup keys, duplicate grouping.
- `copy.py` — file copying with collision resolution and sidecar handling.
- `albums.py` — album symlink creation.
- `report.py` — HTML report generation (migration + dedup modes).
- `logging_util.py` — migration logging and progress reporting.
- `cli.py` — entry point orchestrating migration and dedup-scan; defines `MEDIA_EXTENSIONS`.

## Conventions

- Write docstrings for public functions (matching CONTRIBUTING.md); inline comments are
  used for non-obvious logic (e.g. the phase markers in `cli.py`).
- `Path` objects (from `pathlib`) are used throughout instead of string paths.
- Media files are matched against `MEDIA_EXTENSIONS` in `cli.py`.
