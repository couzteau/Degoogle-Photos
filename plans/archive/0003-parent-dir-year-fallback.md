# Plan 0003: Replace mtime fallback with parent-directory year + report discoverability

## Problem

The last step of the date cascade in `dates.py` uses the file's mtime. For a
Google Takeout extract, mtime is just the extraction date — files land in a
meaningless `YYYY/MM/` folder stamped with source `"mtime"`.

## New date behavior

- **Step 5 (replacing mtime):** extract a 4-digit year from the *immediate
  parent directory* name (covers Takeout's
  `Google Photos/Photos from 2015/IMG.jpg` layout). File goes to
  `YYYY/unknown/` with date source `"parent_dir"`.
- **Final resort:** no date anywhere → `(None, "none")` → existing
  `needs_review/` directory (the "unmatched" directory).
- mtime is removed from the cascade entirely.

New cascade: `EXIF > JSON photoTakenTime > filename > JSON creationTime >
parent dir year > none (needs_review)`.

## Code changes

### `degoogle_photos/dates.py`

- Delete `_date_from_mtime` and cascade step 5.
- Add `_year_from_parent_dir(media_path) -> Optional[int]`: regex
  `(?<!\d)((?:19|20)\d{2})(?!\d)` on `media_path.parent.name`, validated
  1970–2030 (consistent with the filename-pattern check).
- New step 5: return `(datetime(year, 1, 1), "parent_dir")` — the datetime is
  a year carrier; the `"parent_dir"` label routes it to the `unknown` month
  folder.
- Update module docstring.

### `degoogle_photos/copy.py`

- `compute_dest_path` gains optional `date_source: Optional[str] = None`:
  when `"parent_dir"` → `output_root/YYYY/unknown/filename`. Default `None`
  preserves existing behavior.

### `degoogle_photos/cli.py`

- Pass `date_source` to `compute_dest_path` at both call sites (migration
  line ~245; dedup line ~110 — `_date_source` no longer discarded).
- In `_run_dedup`, after computing `dest`, report files needing attention:
  `report.add_attention(src, dest, date_source)` when
  `date_source in ("parent_dir", "none")`.

## Report discoverability (`degoogle_photos/report.py`)

Goal: `unknown` and unmatched (`needs_review`) directories must be easily
discoverable in the HTML reports.

### Migration report (`HtmlReport`)

1. `add_copied`: folder key becomes `YYYY/unknown` when
   `date_source == "parent_dir"` (report pages match on-disk layout).
2. **New "Attention needed" section** on the index page, directly after
   Summary, rendered only when such folders are non-empty:
   - `needs_review` — "No date found from any source", count, link to its
     folder page.
   - Each `YYYY/unknown` — "Year known from parent folder, month unknown",
     count, link.
   - Warning-orange styling (new `.attention` CSS block).
3. **Summary stats:** make "Needs review" a link to
   `folder_needs_review.html`; add an "Unknown month" stat (total files
   across `*/unknown` folders), linked — both rendered only when > 0.
4. **Folder navigation:** extend the existing orange `review` CSS class to
   `*/unknown` links too, so they stand out in "Browse by Date Folder".
5. **Folder pages:** explanatory subtitle under the `<h1>` for
   `needs_review` and `YYYY/unknown` pages.
6. Date-source table: replace `"mtime"` label with
   `"parent_dir": "Parent directory year"`; update ordered key list.
   CSS: rename `.badge-mtime` → `.badge-parent_dir`.

### Dedup report (`DedupReport`)

7. New `add_attention(src, dest, date_source)` collecting files that landed
   in `needs_review/` or `YYYY/unknown/`.
8. New **"Files Needing Attention"** section on the dedup index page
   (rendered only when non-empty): two groups — *Unmatched (no date)* and
   *Unknown month* — each row showing source path, destination path, and a
   copy-path button, so these files are discoverable without browsing the
   output tree manually.

## Tests

- `test_dates.py`: drop `test_date_from_mtime` /
  `test_extract_date_mtime_fallback` and the `_date_from_mtime` import; add
  `_year_from_parent_dir` tests (match, no match, out-of-range,
  digit-boundary like `12015`), `extract_date` → `"parent_dir"` from a
  `Photos from 2015` folder, and full no-date → `(None, "none")`.
- `test_copy.py`: `compute_dest_path(..., date_source="parent_dir")` →
  `YYYY/unknown/`.
- `test_dedup_mode.py`: update `test_no_date_file_goes_to_needs_review` —
  its comments are now stale; with mtime gone, a dateless file in a year-less
  folder lands in `needs_review/`, so assert that explicitly.
- `test_report.py`: assert index HTML contains the "Attention needed" section
  with `needs_review` and `YYYY/unknown` links when such files are added;
  assert `YYYY/unknown` folder key from `add_copied` with
  `date_source="parent_dir"`.

## Docs

- `README.md` (lines 37, 174, 204) and `AGENTS.md` (lines 17, 67): cascade
  becomes `EXIF > JSON photoTakenTime > filename > JSON creationTime >
  parent dir year`, noting `YYYY/unknown/` and `needs_review/` destinations
  and the report's "Attention needed" section.

## Verification

`pytest -v` — full suite green, with the updated tests covering the new
cascade and report sections.
