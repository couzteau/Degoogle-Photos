# Plan: Read nested EXIF created-date with flat fallback

## Root cause

`dates._date_from_exif()` does flat lookups on `img.getexif()`. Per the EXIF spec,
`DateTimeOriginal` (unsigned byte `0x9003`, tag 36867) and `DateTimeDigitized` (`0x9004`,
36868) typically live in the **EXIF sub-IFD**, reached via IFD 0's `ExifOffset` pointer tag
(`0x8769`). Pillow's `getexif()` surfaces IFD 0 only, so nested values are invisible unless
accessed via `exif.get_ifd(0x8769)` (available since Pillow 9.1). Verified locally: nested
DateTimeOriginal returns `None` from flat lookup but reads correctly via `get_ifd`.

## Design

Priority 1 = nested EXIF sub-IFD; priority 2 = flat IFD 0 fallback. Complexity isolated
inside two helpers so `_date_from_exif` reads sequentially.

## Step 1 — dependency floor bump

`pyproject.toml`: `dependencies = ["Pillow>=9.0"]` → `["Pillow>=9.1"]`.

## Step 2 — failing tests (TDD)

In `tests/test_dates.py`, helper to build synthetic JPEGs with nested EXIF:

```python
def _make_jpeg_with_nested_exif(path: Path, exif_sub_ifd: dict) -> None:
    from PIL import Image
    img = Image.new("RGB", (1, 1), "white")
    exif = Image.Exif()
    exif[0x8769] = exif_sub_ifd
    img.save(path, exif=exif)
```

New tests (expected to fail pre-fix):

- `test_date_from_exif_nested_dto`
- `test_extract_date_exif_nested_source` (source must become `"exif"`, not `"mtime"`)
- `test_date_from_exif_flat_fallback` (regression for plain IFD 0)

`PIL.Image` imported locally per project convention.

## Step 3 — confirm failure

`pytest -v tests/test_dates.py -k exif` — new tests fail, existing pass.

## Step 4 — implement in `degoogle_photos/dates.py`

```python
EXIF_SUB_IFD_TAG = 0x8769
EXIF_DATETIME_TAGS = (36867, 36868, 306)   # DTO, Digitized, DateTime
EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"


def _date_from_exif(media_path: Path) -> Optional[datetime]:
    ext = media_path.suffix.lower()
    if ext not in {".jpg", ".jpeg", ".tiff", ".tif", ".png"}:
        return None
    try:
        from PIL import Image
        with Image.open(media_path) as img:
            exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    return _parse_first_datetime(_exif_datetime_tags(exif))


def _exif_datetime_tags(exif) -> list:
    """Candidate values: nested sub-IFD first, flat fallback."""
    candidates = []
    for tag_id in EXIF_DATETIME_TAGS:
        val = exif.get_ifd(EXIF_SUB_IFD_TAG).get(tag_id) or exif.get(tag_id)
        if val:
            candidates.append(val)
    return candidates


def _parse_first_datetime(values) -> Optional[datetime]:
    for val in values:
        try:
            dt = datetime.strptime(val, EXIF_DATE_FORMAT)
            if dt.year >= 1970:
                return dt
        except (ValueError, TypeError):
            continue
    return None
```

## Step 5 — verify

- `pytest -v tests/test_dates.py`
- `pytest -v`
- Remove scratch file `/tmp/opencode/nested_exif.jpg` from analysis.

## Scope / non-goals

- `metadata.py` untouched (reads IFD 0 fields; GPS already uses `get_ifd` correctly).
- Cascade labels unchanged (`"exif"` source string stays).
- No `AGENTS.md` structural updates needed for the fix itself (plan is already referenced).

## Est.

~45 LOC total (mostly tests).
