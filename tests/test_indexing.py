"""Tests for degoogle_photos.indexing."""

import json
from pathlib import Path

from degoogle_photos.indexing import (
    find_takeout_dirs,
    build_index,
    _strip_sidecar_suffix,
    _parse_sidecar_name,
    find_json_for_media,
    find_all_media_files,
)


MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".mov"}


def test_find_takeout_dirs(fake_takeout):
    dirs = find_takeout_dirs(fake_takeout)
    assert len(dirs) == 1
    assert dirs[0].name == "Google Photos"


def test_find_takeout_dirs_ignores_non_takeout(tmp_path):
    (tmp_path / "NotTakeout" / "Google Photos").mkdir(parents=True)
    (tmp_path / "Takeout1" / "Google Photos").mkdir(parents=True)
    dirs = find_takeout_dirs(tmp_path)
    assert len(dirs) == 1


def test_find_takeout_dirs_pointed_at_takeout_dir(tmp_path):
    """Case 2: user points --source at the Takeout dir itself."""
    takeout = tmp_path / "Takeout"
    (takeout / "Google Photos" / "Album1").mkdir(parents=True)
    dirs = find_takeout_dirs(takeout)
    assert len(dirs) == 1
    assert dirs[0].name == "Google Photos"


def test_find_takeout_dirs_pointed_at_google_photos(tmp_path):
    """Case 3: user points --source at the Google Photos dir."""
    gp = tmp_path / "Takeout" / "Google Photos"
    (gp / "Album1").mkdir(parents=True)
    dirs = find_takeout_dirs(gp)
    assert len(dirs) == 1
    assert dirs[0] == gp


def test_find_takeout_dirs_grandparent(tmp_path):
    """Case 4: user points --source one level above the Takeout dirs."""
    (tmp_path / "export1" / "Takeout" / "Google Photos").mkdir(parents=True)
    (tmp_path / "export2" / "Takeout" / "Google Photos").mkdir(parents=True)
    dirs = find_takeout_dirs(tmp_path)
    assert len(dirs) == 2


def test_build_index(fake_takeout):
    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    # Should find photo.jpg and video.mp4
    assert len(media) == 2
    names = {p.name for p, _ in media}
    assert "photo.jpg" in names
    assert "video.mp4" in names
    # JSON index should have photo.jpg via title
    assert "photo.jpg" in json_idx["album1"]


def test_build_index_skips_metadata_json(fake_takeout):
    dirs = find_takeout_dirs(fake_takeout)
    _, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    # metadata.json's title "Album1" should not appear as a media key
    album_keys = json_idx.get("album1", {})
    assert "metadata.json" not in album_keys


def test_strip_sidecar_suffix():
    assert _strip_sidecar_suffix("photo.jpg.json") == "photo.jpg"
    assert _strip_sidecar_suffix("photo.jpg.supplemental-metadata.json") == "photo.jpg"
    assert _strip_sidecar_suffix("photo.jpg.suppl.json") == "photo.jpg"
    assert _strip_sidecar_suffix("photo.jpg.supp.json") == "photo.jpg"
    assert _strip_sidecar_suffix("photo.jpg.sup.json") == "photo.jpg"
    assert _strip_sidecar_suffix("not_a_sidecar.txt") is None


def test_find_json_for_media_direct_match(fake_takeout):
    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    photo = [p for p, _ in media if p.name == "photo.jpg"][0]
    result = find_json_for_media(photo, "Album1", json_idx)
    assert result is not None
    assert result.name == "photo.jpg.json"


def test_find_json_for_media_no_match(fake_takeout):
    dirs = find_takeout_dirs(fake_takeout)
    _, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    fake_media = fake_takeout / "Takeout1" / "Google Photos" / "Album1" / "nonexistent.jpg"
    result = find_json_for_media(fake_media, "Album1", json_idx)
    assert result is None


def test_find_json_for_media_prefix_match(tmp_path):
    """Test prefix matching for truncated JSON titles."""
    album_dir = tmp_path / "Takeout1" / "Google Photos" / "Album1"
    album_dir.mkdir(parents=True)

    # Long media filename
    long_name = "a" * 20 + "_extra_stuff.jpg"
    (album_dir / long_name).write_bytes(b"\xff\xd8\xff\xd9")

    # JSON with truncated title (only first 20 chars)
    truncated_title = "a" * 20
    sidecar = {"title": truncated_title}
    (album_dir / (truncated_title + ".json")).write_text(
        json.dumps(sidecar), encoding="utf-8"
    )

    dirs = find_takeout_dirs(tmp_path)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    media_file = [p for p, _ in media][0]
    result = find_json_for_media(media_file, "Album1", json_idx)
    assert result is not None


def test_parse_sidecar_name():
    assert _parse_sidecar_name("photo.jpg.json") == ("photo.jpg", None)
    assert _parse_sidecar_name("photo.jpg.supplemental-metadata.json") == ("photo.jpg", None)
    assert _parse_sidecar_name("IMG_0003.HEIC.supplemental-metadata(1).json") == ("IMG_0003.HEIC", "1")
    assert _parse_sidecar_name("IMG_0003.HEIC.supplemental(2).json") == ("IMG_0003.HEIC", "2")
    assert _parse_sidecar_name("IMG_0003.HEIC.sup(3).json") == ("IMG_0003.HEIC", "3")
    assert _parse_sidecar_name("IMG_0003.HEIC(1).json") is None  # plain short form not handled
    assert _parse_sidecar_name("not_a_sidecar.txt") is None


def test_build_index_dup_sidecar_matching(fake_takeout):
    """Album with a photo and its (1) duplicate, each with its own sidecar."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album2"
    album_dir.mkdir(parents=True)
    (album_dir / "IMG_0003.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003(1).jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003.jpg.supplemental-metadata.json").write_text(
        json.dumps({"title": "IMG_0003.jpg"}), encoding="utf-8"
    )
    (album_dir / "IMG_0003.jpg.supplemental-metadata(1).json").write_text(
        json.dumps({"title": "IMG_0003(1).jpg"}), encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    orig = [p for p, _ in media if p.name == "IMG_0003.jpg" and p.parent.name == "Album2"][0]
    dup = [p for p, _ in media if p.name == "IMG_0003(1).jpg" and p.parent.name == "Album2"][0]

    assert find_json_for_media(orig, "Album2", json_idx).name == "IMG_0003.jpg.supplemental-metadata.json"
    assert find_json_for_media(dup, "Album2", json_idx).name == "IMG_0003.jpg.supplemental-metadata(1).json"


def test_build_index_dup_sidecar_malformed(fake_takeout):
    """Dup sidecar has no title, so only the strip/reconstruction path can match."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album2b"
    album_dir.mkdir(parents=True)
    (album_dir / "IMG_0003.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003(1).jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003.jpg.supplemental-metadata.json").write_text(
        json.dumps({"title": "IMG_0003.jpg"}), encoding="utf-8"
    )
    (album_dir / "IMG_0003.jpg.supplemental-metadata(1).json").write_text(
        "not json", encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    dup = [p for p, _ in media if p.name == "IMG_0003(1).jpg" and p.parent.name == "Album2b"][0]

    assert find_json_for_media(dup, "Album2b", json_idx).name == "IMG_0003.jpg.supplemental-metadata(1).json"


def test_build_index_edited_sidecar_inheritance(fake_takeout):
    """An -edited file with no sidecar inherits the original's sidecar."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album3"
    album_dir.mkdir(parents=True)
    (album_dir / "img.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "img-edited.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "img.jpg.json").write_text(
        json.dumps({"title": "img.jpg"}), encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    edited = [p for p, _ in media if p.name == "img-edited.jpg" and p.parent.name == "Album3"][0]

    assert find_json_for_media(edited, "Album3", json_idx).name == "img.jpg.json"


def test_build_index_edited_own_sidecar_preferred(fake_takeout):
    """An -edited file with its own sidecar prefers it over the original's."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album4"
    album_dir.mkdir(parents=True)
    (album_dir / "img.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "img-edited.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "img.jpg.json").write_text(
        json.dumps({"title": "img.jpg"}), encoding="utf-8"
    )
    (album_dir / "img-edited.jpg.json").write_text(
        json.dumps({"title": "img-edited.jpg"}), encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    edited = [p for p, _ in media if p.name == "img-edited.jpg" and p.parent.name == "Album4"][0]

    assert find_json_for_media(edited, "Album4", json_idx).name == "img-edited.jpg.json"


def test_build_index_edited_uppercase(fake_takeout):
    """The -edited fallback is case-insensitive (-EDITED)."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album5"
    album_dir.mkdir(parents=True)
    (album_dir / "IMG_5.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_5-EDITED.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_5.jpg.supplemental-metadata.json").write_text(
        json.dumps({"title": "IMG_5.jpg"}), encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    edited = [p for p, _ in media if p.name == "IMG_5-EDITED.jpg" and p.parent.name == "Album5"][0]

    assert find_json_for_media(edited, "Album5", json_idx).name == "IMG_5.jpg.supplemental-metadata.json"


def test_find_json_for_media_dup_fallback(fake_takeout):
    """A (1)-renamed file falls back to the original's sidecar when no (1) sidecar exists."""
    album_dir = fake_takeout / "Takeout1" / "Google Photos" / "Album6"
    album_dir.mkdir(parents=True)
    (album_dir / "IMG_0003.jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003(1).jpg").write_bytes(b"\x00" * 20)
    (album_dir / "IMG_0003.jpg.supplemental-metadata.json").write_text(
        json.dumps({"title": "IMG_0003.jpg"}), encoding="utf-8"
    )

    dirs = find_takeout_dirs(fake_takeout)
    media, json_idx = build_index(dirs, MEDIA_EXTENSIONS)
    dup = [p for p, _ in media if p.name == "IMG_0003(1).jpg" and p.parent.name == "Album6"][0]

    assert find_json_for_media(dup, "Album6", json_idx).name == "IMG_0003.jpg.supplemental-metadata.json"


# ---------------------------------------------------------------------------
# find_all_media_files
# ---------------------------------------------------------------------------

def test_find_all_media_files_flat(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"x")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "readme.txt").write_bytes(b"x")  # should be ignored
    found = find_all_media_files(tmp_path, MEDIA_EXTENSIONS)
    names = {f.name for f in found}
    assert names == {"photo.jpg", "clip.mp4"}


def test_find_all_media_files_nested(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "nested.jpg").write_bytes(b"x")
    (tmp_path / "top.jpg").write_bytes(b"x")
    found = find_all_media_files(tmp_path, MEDIA_EXTENSIONS)
    assert len(found) == 2


def test_find_all_media_files_case_insensitive_extensions(tmp_path):
    (tmp_path / "photo.JPG").write_bytes(b"x")
    (tmp_path / "photo.JPEG").write_bytes(b"x")
    found = find_all_media_files(tmp_path, MEDIA_EXTENSIONS)
    assert len(found) == 2


def test_find_all_media_files_empty_dir(tmp_path):
    assert find_all_media_files(tmp_path, MEDIA_EXTENSIONS) == []
