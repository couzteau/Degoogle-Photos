# Plan 0004: Live Photo pair inheritance + mislabeled-video fix

## Problem

After a migration, files landing in `YYYY/unknown/` and `needs_review/` are
disproportionately iPhone content. Root cause confirmed by research (Google
Support threads, r/googlephotos, joelkitching.com):

1. **iPhone Live Photos are stored by Google Photos as two separate files** —
   a still (`IMG_1234.HEIC`) and a ~3s video (`IMG_1234.MP4`, the MOV part
   re-containered).
2. **Takeout exports them as separate files, but typically only ONE JSON
   sidecar** — for the still. The extracted MP4 gets no sidecar.
3. Walking `dates.extract_date()` for such an MP4: EXIF fails (Pillow can't
   read video), no JSON sidecar exists, `IMG_1234` has no filename date, and
   the parent dir is only useful in `Photos from YYYY` albums. Result:
   `YYYY/unknown/` (year only) or `needs_review/` (nothing).

Secondary confirmed Takeout bug: sometimes the Live Photo **video part is
mislabeled** `IMG_1234(1).HEIC` (video bytes, wrong extension). It already gets
a *date* via plan 0002's `(N)` fallback, but is copied out with a `.heic`
extension and won't play as a video.

## Scope (confirmed with user)

- **Part 1:** Live Photo pair inheritance (video inherits same-stem still's sidecar).
- **Part 2:** Fix the `(1).HEIC`-is-actually-video bug via magic-byte sniffing.
- Keep existing date-source labels (no new `live_photo_pair` label).
- No HEIC EXIF support (no `pillow-heif` dependency).
- No verification against real Takeout data (not reachable from this machine).
- **Finder/report button: leave as-is** (out of scope).

Non-goals: recombining pairs into single motion-photo files; dedup-mode sibling
date inheritance (dedup mode has no JSON index by design).

## Part 1 — Live Photo pair inheritance (`degoogle_photos/indexing.py`)

- New helper `_live_photo_still_names(media_name: str) -> List[str]`:
  for `.mp4`/`.mov` files only, return same-stem still candidates
  (`IMG_1234.MP4` → `IMG_1234.heic`, `.jpg`, `.jpeg`); empty list otherwise.
- In `find_json_for_media`, insert a new stage **after** the direct-candidate
  match (a file's own sidecar always wins) and **before** prefix matching
  (exact stem equality beats fuzz):
  - For each name from `_media_name_candidates()` (so a renamed
    `IMG_1234(1).MP4` also resolves via `IMG_1234.HEIC`), try exact index hits
    for the still names.
  - Same album only (the index is per-album; pairs always live in the same
    Takeout folder).

Downstream effect: the MP4 gets a date (`json_taken`/`json_created`, labels
unchanged), report metadata, and a copied sidecar alongside the video — the
same inheritance pattern plan 0002 established for `-edited`/`(N)` files.

## Part 2 — `(1).HEIC`-is-actually-video fix

- **New module `degoogle_photos/sniff.py`**: `effective_media_name(path) -> str`.
  For `.heic` files only, read the first 12 bytes; if it is an ISO-BMFF
  container (`ftyp` at offset 4) whose major brand is a **video** brand
  (`isom`, `mp41`, `mp42`, `avc1`, `M4V `, …) → return the name with `.mp4`;
  brand `qt  ` → `.mov`. HEIC brands (`heic`, `heix`, `mif1`, …), unreadable,
  or missing files → original name (conservative).
- **`copy.py`**: `compute_dest_path` gains an optional `dest_name=None`
  parameter (pure path math, no I/O — existing tests unaffected).
- **`cli.py`**: both call sites (migration loop + dedup phase 3) pass
  `effective_media_name(...)`. Resume check, sidecar copy-rename, report, and
  album/by-folder symlinks all follow automatically.

## Tests

- `tests/test_indexing.py`: MP4/MOV inherits same-stem HEIC sidecar; own
  sidecar wins; `(1).MP4` inherits; no same-stem still → `None`; stills never
  inherit from stills; different-stem video → `None`.
- New `tests/test_sniff.py`: crafted 12-byte headers per brand, missing/short/
  non-heic files.
- `tests/test_copy.py`: `dest_name` override across dated/`unknown`/
  `needs_review` paths.

## Housekeeping

- `AGENTS.md`: add `sniff.py` to code organization; mention Live Photo
  inheritance in the overview.
- Check README's documented matching rules; update if needed.
- This file is `plans/0004-live-photo-pair-inheritance.md`; on completion move
  to `plans/archive/` with `git mv` (folder position is the status marker).

## Verification

- `pytest -v tests/test_indexing.py tests/test_sniff.py tests/test_copy.py`
- Full `pytest -v`
