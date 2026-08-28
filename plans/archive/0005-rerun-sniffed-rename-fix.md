# Plan 0005: Rerun-safe resume for sniffed renames

## Problem

Code review of plan 0004 flagged a rerun duplication bug:

- Plan 0004 renamed mislabeled `.heic`-as-video files at copy time
  (`sniff.effective_media_name`), and the migration loop's resume check
  (`copy.is_already_copied`) tests the sniffed destination name.
- A user who ran the migration **before** plan 0004 has the mislabeled file at
  `YYYY/MM/IMG_1.HEIC` in the output. On rerun, the sniffed dest is
  `YYYY/MM/IMG_1.mp4`, the resume check misses the old file, and it is copied
  again — leaving both the wrongly-named and correctly-named file in the
  output.

Dedup-mode's phase 3 copies unconditionally for every rerun anyway (by design,
no resume check there), so this only affects migration mode's resume path.

## Scope

- Fix the migration-mode resume check so a rerun after the plan 0004 rename
  feature does not duplicate plan-0004-era output.
- In a real (non-dry-run) rerun, rename the existing wrongly-named destination
  file in place (no re-copy); its sidecar (`<name>.json`) is renamed
  alongside. In dry-run, detect and count as resume without touching the
  filesystem.
- Non-goals: dedup mode (has no resume check by design), stale-broken-album
  symlink cleanup (cosmetic; stale links point to the old name, links are
  harmless).

## Implementation

`degoogle_photos/copy.py` — new function:

```python
def fix_rename_resume(media_path: Path, dest_path: Path) -> None:
    """If dest_path's stem differs from media_path's (sniffed rename), and an
    old wrongly-named file exists at media_path's original name while
    dest_path does not yet exist, rename it (and its sidecar) in place.

    Pure guard: returns immediately when names match, dest already exists, or
    the old-name file is absent.
    """
```

- Only acts when `media_path.name != dest_path.name` (i.e. sniffed rename) —
  normal resume behaviour unchanged for all other files.
- Rename `old` (original name) → `dest_path` via `Path.rename`; rename the
  sidecar `old.name + ".json"` similarly when present.
- `cli.py` migration loop: call `fix_rename_resume(media_path, dest_path)`
  right before `is_already_copied(...)` — but only when not dry-run, since it
  performs real I/O. Detection costs nothing in dry-run because the check is
  purely `not dest_path.exists() and old.exists()`.

`cli.py` change sketch:

```python
if not dry_run:
    fix_rename_resume(media_path, dest_path)
if is_already_copied(media_path, dest_path):
    ...
```

Edge cases:

- Both old-name file and sniffed dest exist (partial rerun): no rename;
  `is_already_copied` on dest still returns True → resume skip fires; the old
  file is left alone (extremely rare, acceptable).
- Rename target sidecar collision is impossible in practice (same directory,
  and old sidecar carries the old name).

## Tests

`tests/test_copy.py`:

- Old `<original>.HEIC` file + `.json` exist in dest dir → after
  `fix_rename_resume`, file renamed to sniffed dest; sidecar renamed;
  `is_already_copied` then True.
- Old file present, dest already exists → no rename; both files unchanged.
- Media name == dest name (no sniff) → no-op even with old file present.
- Old file absent → no-op, no exception.
- No sidecar → media renamed without error.
- End-to-end through `cli.py`: build output, place old-name file, rerun
  migration, assert single file in `YYYY/MM/` and `skipped_resume == 1`.

## Housekeeping

- `AGENTS.md`: mention the rename-aware resume in the migration overview
  bullet (one sentence).

## Verification

- `pytest -v tests/test_copy.py`
- Full `pytest -v`
