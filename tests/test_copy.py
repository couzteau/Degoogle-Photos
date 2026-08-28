"""Tests for degoogle_photos.copy."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from degoogle_photos.cli import main
from degoogle_photos.copy import (
    compute_dest_path,
    resolve_collision,
    is_already_copied,
    copy_with_sidecar,
    fix_rename_resume,
    sniffed_rename_old_path,
)


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """Prevent tests from opening a web browser."""
    monkeypatch.setattr("webbrowser.open", lambda *a, **kw: None)


def test_compute_dest_path_with_date(output_dir):
    dt = datetime(2020, 5, 10)
    media = Path("/fake/photo.jpg")
    dest = compute_dest_path(output_dir, media, dt)
    assert dest == output_dir / "2020" / "05" / "photo.jpg"


def test_compute_dest_path_without_date(output_dir):
    media = Path("/fake/photo.jpg")
    dest = compute_dest_path(output_dir, media, None)
    assert dest == output_dir / "needs_review" / "photo.jpg"


def test_compute_dest_path_parent_dir(output_dir):
    dt = datetime(2015, 1, 1)
    media = Path("/fake/photo.jpg")
    dest = compute_dest_path(output_dir, media, dt, date_source="parent_dir")
    assert dest == output_dir / "2015" / "unknown" / "photo.jpg"


def test_compute_dest_path_dest_name_dated(output_dir):
    """dest_name overrides the destination filename (dated path)."""
    dt = datetime(2020, 5, 10)
    media = Path("/fake/IMG_1234.HEIC")
    dest = compute_dest_path(output_dir, media, dt, dest_name="IMG_1234.mp4")
    assert dest == output_dir / "2020" / "05" / "IMG_1234.mp4"


def test_compute_dest_path_dest_name_unknown(output_dir):
    dt = datetime(2015, 1, 1)
    media = Path("/fake/IMG_1234.HEIC")
    dest = compute_dest_path(
        output_dir, media, dt, date_source="parent_dir", dest_name="IMG_1234.mp4"
    )
    assert dest == output_dir / "2015" / "unknown" / "IMG_1234.mp4"


def test_compute_dest_path_dest_name_needs_review(output_dir):
    media = Path("/fake/IMG_1234.HEIC")
    dest = compute_dest_path(output_dir, media, None, dest_name="IMG_1234.mp4")
    assert dest == output_dir / "needs_review" / "IMG_1234.mp4"


def test_resolve_collision_no_conflict(tmp_path):
    dest = tmp_path / "photo.jpg"
    assert resolve_collision(dest) == dest


def test_resolve_collision_appends_counter(tmp_path):
    dest = tmp_path / "photo.jpg"
    dest.write_bytes(b"existing")
    resolved = resolve_collision(dest)
    assert resolved == tmp_path / "photo_2.jpg"


def test_resolve_collision_increments(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"x")
    (tmp_path / "photo_2.jpg").write_bytes(b"x")
    resolved = resolve_collision(tmp_path / "photo.jpg")
    assert resolved == tmp_path / "photo_3.jpg"


def test_is_already_copied_same_size(tmp_path):
    src = tmp_path / "source.jpg"
    dst = tmp_path / "dest.jpg"
    content = b"hello world"
    src.write_bytes(content)
    dst.write_bytes(content)
    assert is_already_copied(src, dst) is True


def test_is_already_copied_different_size(tmp_path):
    src = tmp_path / "source.jpg"
    dst = tmp_path / "dest.jpg"
    src.write_bytes(b"hello")
    dst.write_bytes(b"hi")
    assert is_already_copied(src, dst) is False


def test_is_already_copied_no_dest(tmp_path):
    src = tmp_path / "source.jpg"
    src.write_bytes(b"hello")
    assert is_already_copied(src, tmp_path / "nope.jpg") is False


def _write_sidecar(dir_path: Path, name: str) -> Path:
    """Write a JSON sidecar `name` inside `dir_path` and return its path."""
    sidecar = dir_path / name
    sidecar.write_text(f'{{"title": "{name}"}}', encoding="utf-8")
    return sidecar


def test_fix_rename_resume_renames_old_file_and_sidecar(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    media.write_bytes(b"video bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)

    (dest.parent / "IMG_1.HEIC").write_bytes(b"video bytes")
    _write_sidecar(dest.parent, "IMG_1.HEIC.json")

    fix_rename_resume(media, dest)

    assert dest.read_bytes() == b"video bytes"
    assert not (dest.parent / "IMG_1.HEIC").exists()
    assert (dest.parent / "IMG_1.mp4.json").exists()
    assert not (dest.parent / "IMG_1.HEIC.json").exists()
    assert is_already_copied(media, dest) is True


def test_fix_rename_resume_dest_exists_no_rename(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    media.write_bytes(b"video bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)

    (dest.parent / "IMG_1.HEIC").write_bytes(b"old bytes")
    dest.write_bytes(b"new bytes")

    fix_rename_resume(media, dest)

    assert (dest.parent / "IMG_1.HEIC").read_bytes() == b"old bytes"
    assert dest.read_bytes() == b"new bytes"


def test_fix_rename_resume_same_name_noop(tmp_path):
    """Matching names (no sniff rename) never triggers, even with a dest file present."""
    media = tmp_path / "source" / "IMG_1.jpg"
    media.parent.mkdir()
    media.write_bytes(b"photo bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.jpg"
    dest.parent.mkdir(parents=True)

    (dest.parent / "IMG_1.jpg").write_bytes(b"old bytes")

    fix_rename_resume(media, dest)

    assert (dest.parent / "IMG_1.jpg").read_bytes() == b"old bytes"


def test_fix_rename_resume_old_absent_noop(tmp_path):
    """Absent old-name file is a pure no-op with no exception."""
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    media.write_bytes(b"video bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"

    fix_rename_resume(media, dest)

    assert not dest.exists()


def test_fix_rename_resume_without_sidecar(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    media.write_bytes(b"video bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)

    (dest.parent / "IMG_1.HEIC").write_bytes(b"video bytes")

    fix_rename_resume(media, dest)

    assert dest.read_bytes() == b"video bytes"
    assert not (dest.parent / "IMG_1.HEIC").exists()


def test_fix_rename_resume_sidecar_dest_exists(tmp_path):
    """An existing new-name sidecar is left untouched, not overwritten."""
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    media.write_bytes(b"video bytes")
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)

    (dest.parent / "IMG_1.HEIC").write_bytes(b"video bytes")
    _write_sidecar(dest.parent, "IMG_1.HEIC.json")
    sidecar_dest = dest.parent / "IMG_1.mp4.json"
    sidecar_dest.write_text('{"existing": true}', encoding="utf-8")

    fix_rename_resume(media, dest)

    assert dest.read_bytes() == b"video bytes"
    assert sidecar_dest.read_text(encoding="utf-8") == '{"existing": true}'


def test_sniffed_rename_old_path_returns_old(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)
    (dest.parent / "IMG_1.HEIC").write_bytes(b"video bytes")

    old = sniffed_rename_old_path(media, dest)

    assert old == dest.parent / "IMG_1.HEIC"


def test_sniffed_rename_old_path_none_when_same_name(tmp_path):
    media = tmp_path / "source" / "IMG_1.jpg"
    media.parent.mkdir()
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.jpg"
    dest.parent.mkdir(parents=True)
    (dest.parent / "IMG_1.jpg").write_bytes(b"bytes")

    assert sniffed_rename_old_path(media, dest) is None


def test_sniffed_rename_old_path_none_when_dest_exists(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)
    (dest.parent / "IMG_1.HEIC").write_bytes(b"old bytes")
    dest.write_bytes(b"new bytes")

    assert sniffed_rename_old_path(media, dest) is None


def test_sniffed_rename_old_path_none_when_old_absent(tmp_path):
    media = tmp_path / "source" / "IMG_1.HEIC"
    media.parent.mkdir()
    dest = tmp_path / "output" / "2020" / "05" / "IMG_1.mp4"
    dest.parent.mkdir(parents=True)

    assert sniffed_rename_old_path(media, dest) is None


def test_copy_with_sidecar(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    out = tmp_path / "output" / "2020" / "05"

    media = src / "photo.jpg"
    media.write_bytes(b"jpeg data")
    sidecar = src / "photo.jpg.json"
    sidecar.write_text('{"title":"photo.jpg"}', encoding="utf-8")

    dest = out / "photo.jpg"
    actual = copy_with_sidecar(media, sidecar, dest, dry_run=False)

    assert actual.exists()
    assert actual.read_bytes() == b"jpeg data"
    json_copy = actual.parent / (actual.name + ".json")
    assert json_copy.exists()


def test_copy_with_sidecar_dry_run(tmp_path):
    media = tmp_path / "photo.jpg"
    media.write_bytes(b"data")
    dest = tmp_path / "output" / "photo.jpg"
    actual = copy_with_sidecar(media, None, dest, dry_run=True)
    # Dry run should not create any files
    assert not actual.exists()


def _ftyp_video_bytes() -> bytes:
    """A minimal ISO-BMFF 'isom' header over dummy video payload."""
    size = (12).to_bytes(4, "big")
    return size + b"ftyp" + b"isom" + b"videodata"


def _run_migration(monkeypatch, source, output):
    monkeypatch.setattr(
        sys, "argv", ["pytest", "--source", str(source), "--output", str(output)]
    )
    main()
def test_migration_rerun_renames_sniffed_dest(tmp_path, monkeypatch):
    """A rerun over plan-0004-era output renames the wrongly-named file in place."""
    album = tmp_path / "Takeout1" / "Google Photos" / "Album1"
    album.mkdir(parents=True)
    video = _ftyp_video_bytes()
    (album / "IMG_1.HEIC").write_bytes(video)
    (album / "IMG_1.HEIC.json").write_text(
        json.dumps(
            {
                "title": "IMG_1.HEIC",
                "photoTakenTime": {"timestamp": "1589155200"},  # 2020-05-11
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    # First run: the sniffed destination is copied correctly.
    _run_migration(monkeypatch, tmp_path, output)
    bucket = output / "2020" / "05"
    assert (bucket / "IMG_1.mp4").exists()

    # Simulate a pre-plan-0004 rerun base: wrongly-named file + sidecar, no .mp4.
    for p in bucket.iterdir():
        p.unlink()
    (bucket / "IMG_1.HEIC").write_bytes(video)
    (bucket / "IMG_1.HEIC.json").write_text("{}", encoding="utf-8")

    # Rerun: the old file is renamed in place, not copied again.
    _run_migration(monkeypatch, tmp_path, output)
    media_in_bucket = [p for p in bucket.iterdir() if p.suffix != ".json"]
    assert len(media_in_bucket) == 1
    assert media_in_bucket[0].name == "IMG_1.mp4"
    assert (bucket / "IMG_1.mp4.json").exists()
    log_text = (output / "migration_log.txt").read_text(encoding="utf-8")
    assert "Skipped (already copied): 1" in log_text


def test_migration_rerun_dry_run_counts_resume(tmp_path, monkeypatch, capsys):
    """Dry-run detects the sniffed-rename resume without touching the filesystem."""
    album = tmp_path / "Takeout1" / "Google Photos" / "Album1"
    album.mkdir(parents=True)
    video = _ftyp_video_bytes()
    (album / "IMG_1.HEIC").write_bytes(video)
    (album / "IMG_1.HEIC.json").write_text(
        json.dumps(
            {
                "title": "IMG_1.HEIC",
                "photoTakenTime": {"timestamp": "1589155200"},  # 2020-05-11
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    bucket = output / "2020" / "05"
    bucket.mkdir(parents=True)
    (bucket / "IMG_1.HEIC").write_bytes(video)
    (bucket / "IMG_1.HEIC.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["pytest", "--source", str(tmp_path), "--output", str(output), "--dry-run"],
    )
    main()

    captured = capsys.readouterr()
    assert (bucket / "IMG_1.HEIC").exists()
    assert not (bucket / "IMG_1.mp4").exists()
    assert "Skipped (already copied): 1" in captured.out
