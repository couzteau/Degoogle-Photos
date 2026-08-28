# Plan 0002: Fix JSON sidecar matching for renamed/edited files

## Problem

Google Photos exports rename files in two common ways that break sidecar matching:

1. **`-edited` suffix** — when a photo is edited in Google Photos, a new file like
   `img_5_1734391186378-edited.jpg` is created, but no new sidecar JSON is exported.
   The original's sidecar (`img_5_1734391186378.jpg.supplemental-metadata.json`)
   should apply.
2. **`(N)` suffix** — classic duplicate rename when a filename already exists, e.g.
   `IMG_0003(1).HEIC`. Sidecars are renamed the same way, e.g.
   `IMG_0003.HEIC.supplemental-metadata(1).json`. Current code finds neither.

### Current behavior (`degoogle_photos/indexing.py`)

- `build_index` indexes each sidecar per album under (a) its JSON `title` field and
  (b) its filename with the sidecar suffix stripped (`_strip_sidecar_suffix`).
- `find_json_for_media` tries a direct key match, then a prefix match (≥10 chars).

### Why both cases fail today

1. `-edited`: `img_5_1734391186378-edited.jpg` has no sidecar; the index key is
   `img_5_1734391186378.jpg`. Direct match fails, and prefix match fails because
   `-edited` is inserted *before* the extension, so neither string is a prefix of
   the other.
2. `(N)`: sidecar `IMG_0003.HEIC.supplemental-metadata(1).json` —
   `_strip_sidecar_suffix` only matches the plain `.json` ending, producing the
   garbage key `img_0003.heic.supplemental-metadata(1)`. Lookup for
   `img_0003(1).heic` fails, and prefix matching fails (`img_0003(1).heic` vs
   `img_0003.heic` diverge at char 9). If the JSON title is intact it indexes as
   `img_0003.heic`, which still doesn't match `img_0003(1).heic`.

## Implementation (all in `degoogle_photos/indexing.py` + tests)

### 1. Index-time: parse `(N)` out of sidecar names

- Add `import re` and `_DUP_NUM_RE = re.compile(r"\((\d+)\)$")`.
- New helper `_parse_sidecar_name(json_filename) -> Optional[Tuple[str, Optional[str]]]`
  returning `(media_base, dup_number)`:
  - Exact suffix match (current behavior) → `(base, None)`.
  - Otherwise, for each suffix body (e.g. `.supplemental-metadata` and its
    truncations): if the name is `<base><body>(N).json`, return `(base, N)`. So
    `IMG_0003.HEIC.supplemental-metadata(1).json` → `("IMG_0003.HEIC", "1")`.
- Keep `_strip_sidecar_suffix` as a thin wrapper (existing tests untouched).
- In `build_index`, index the parsed base as today, and when `dup_number` is
  present also index the reconstructed media name via `_insert_dup_number(base, n)`:
  `IMG_0003.HEIC` + `1` → `IMG_0003(1).HEIC`. This gives a direct hit for
  `IMG_0003(1).HEIC` even when the sidecar title is missing/corrupt.
- Deliberately **not** handling the plain short form `IMG_0003.HEIC(1).json`
  (ambiguous with real filenames, and not the pattern in observed exports — flag
  if seen in the wild).

### 2. Lookup-time: fallback candidates in `find_json_for_media`

- New helper `_media_name_candidates(media_name) -> List[str]` (BFS,
  most-specific first), stripping trailing `-edited` and/or `(N)` from the stem:
  - `img_5_1734391186378-edited.jpg` → + `img_5_1734391186378.jpg`
  - `IMG_0003(1).HEIC` → + `IMG_0003.HEIC`
  - combinations like `a(1)-edited.jpg` → `a(1).jpg` → `a.jpg`
- `find_json_for_media` tries a direct index hit for each candidate in order
  (exact name always first, so a file's *own* sidecar always wins), then the
  existing prefix-match stage per candidate (unchanged ≥10-char guard).
- Covers: edited photos inheriting the original's sidecar (via its `title` key),
  and `(N)` files falling back to the original's sidecar when the `(1)` sidecar
  is in another album or missing.

No changes needed in `cli.py`, `dates.py`, `metadata.py`, or `copy.py` — they
just receive a better `json_path` (edited/renamed files will now get dates,
metadata, and a copied sidecar for free). Dedup-scan mode is unaffected (it
ignores sidecars by design).

### 3. Tests (`tests/test_indexing.py`, mirroring existing style)

- `_parse_sidecar_name`: `(1)` form, truncated-suffix+`(2)` form, plain forms,
  non-sidecar.
- Integration via `build_index`: album containing `IMG_0003.HEIC`,
  `IMG_0003(1).HEIC`, both sidecars → each media resolves to its correct
  sidecar; same with a **malformed** `(1)` sidecar (no title → strip-index path).
- Edited: `img.jpg` + sidecar + `img-edited.jpg` → edited resolves to
  original's sidecar; edited file *with* its own sidecar still prefers its own;
  uppercase `-EDITED` variant.
- Lookup fallback: `IMG_0003(1).HEIC` with only the plain sidecar present.
- Existing tests (incl. `no_match`) must still pass.

### 4. Housekeeping

- This file is `plans/0002-sidecar-matching-renamed-files.md`; on completion move
  to `plans/archive/` with `git mv` (folder position is the status marker).
- Check README for a sidecar-pattern list and update if it documents matching
  rules; `AGENTS.md` needs no change (no structural change).

## Verification

- `pytest -v tests/test_indexing.py` then full `pytest -v`.

## Open question (confirm before implementing)

When an edited/renamed file inherits the original's sidecar, `copy_with_sidecar`
will copy that JSON alongside each file (renamed to match each destination) —
so both `img.jpg` and `img-edited.jpg` end up with their own JSON copy in the
output. That seems desirable (metadata travels with each file); confirm whether
to keep that behavior or only copy the sidecar once (with the original).
