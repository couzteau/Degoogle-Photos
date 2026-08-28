"""Tests for degoogle_photos.sniff."""

from pathlib import Path

import pytest

from degoogle_photos.sniff import effective_media_name


def _ftyp_header(major_brand: bytes) -> bytes:
    """A minimal ISO-BMFF 12-byte header: size + 'ftyp' + major brand."""
    size = (12).to_bytes(4, "big")
    return size + b"ftyp" + major_brand


def test_non_heic_files_unchanged(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(_ftyp_header(b"isom"))  # would be video, but not .heic
    assert effective_media_name(p) == "photo.jpg"


def test_video_brand_isom_renamed_to_mp4(tmp_path):
    p = tmp_path / "IMG_1234(1).HEIC"
    p.write_bytes(_ftyp_header(b"isom"))
    assert effective_media_name(p) == "IMG_1234(1).mp4"


@pytest.mark.parametrize(
    "brand",
    [b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"avc3", b"M4V ", b"3gp4"],
)
def test_video_brands_renamed_to_mp4(brand, tmp_path):
    p = tmp_path / "clip.HEIC"
    p.write_bytes(_ftyp_header(brand))
    assert effective_media_name(p) == "clip.mp4"


def test_qt_brand_renamed_to_mov(tmp_path):
    p = tmp_path / "IMG_1234.HEIC"
    p.write_bytes(_ftyp_header(b"qt  "))
    assert effective_media_name(p) == "IMG_1234.mov"


def test_uppercase_heic_extension(tmp_path):
    p = tmp_path / "IMG_1234.HeIc"  # extension matching is case-insensitive
    p.write_bytes(_ftyp_header(b"isom"))
    assert effective_media_name(p) == "IMG_1234.mp4"


@pytest.mark.parametrize(
    "brand",
    [b"heic", b"heix", b"mif1", b"msf1", b"hevc", b"hevx"],
)
def test_heic_brands_unchanged(brand, tmp_path):
    """Genuine HEIC brands are never relabeled."""
    p = tmp_path / "photo.HEIC"
    p.write_bytes(_ftyp_header(brand))
    assert effective_media_name(p) == "photo.HEIC"


def test_not_a_ftyp_container_unchanged(tmp_path):
    p = tmp_path / "photo.HEIC"
    p.write_bytes(b"\x00" * 12)  # no 'ftyp' at offset 4
    assert effective_media_name(p) == "photo.HEIC"


def test_short_file_unchanged(tmp_path):
    p = tmp_path / "photo.HEIC"
    p.write_bytes(b"\x00\x00\x00\x18ftyp")  # only 8 bytes
    assert effective_media_name(p) == "photo.HEIC"


def test_missing_file_unchanged(tmp_path):
    p = tmp_path / "missing.HEIC"
    assert effective_media_name(p) == "missing.HEIC"