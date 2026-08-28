"""Magic-byte sniffing to correct mislabeled media files."""

from pathlib import Path

# ISO-BMFF major brands that identify a file as a video (MP4) container.
# `qt  ` is QuickTime/MOV and is handled separately below. Real HEIC stills use
# `heic`/`heix`/`mif1`/... brands, which are not listed here so they are never
# re-labeled.
_VIDEO_BRANDS = {
    b"isom", b"iso2", b"isoi",
    b"mp41", b"mp42", b"mmp4",
    b"avc1", b"avc2", b"avc3", b"avc4",
    b"M4V ", b"m4v ",
    b"3gp4", b"3gp5", b"3g2a",
}


def _replace_ext(name: str, new_ext: str) -> str:
    """Return `name` with its extension replaced by `new_ext`."""
    return f"{Path(name).stem}{new_ext}"


def effective_media_name(path: Path) -> str:
    """Return the media name, correcting mislabeled video-with-`.heic` files.

    Google occasionally exports the Live Photo video part with a `.heic`
    extension even though the bytes are a video (ISO-BMFF container). For `.heic`
    files only, reads the first 12 bytes and returns the name relabeled as
    `.mp4` (video brand) or `.mov` (QuickTime brand). Everything else —
    non-`.heic` files, missing/unreadable files, short headers, and genuine HEIC
    stills — returns the original name (conservative).
    """
    name = path.name
    if path.suffix.lower() != ".heic":
        return name
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError:
        return name
    if len(header) < 12 or header[4:8] != b"ftyp":
        return name
    major = header[8:12]
    if major == b"qt  ":
        return _replace_ext(name, ".mov")
    if major in _VIDEO_BRANDS:
        return _replace_ext(name, ".mp4")
    return name