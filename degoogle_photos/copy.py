"""File copying with collision resolution and sidecar handling."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


def compute_dest_path(output_root: Path, media_path: Path, dt: Optional[datetime],
                      date_source: Optional[str] = None,
                      dest_name: Optional[str] = None) -> Path:
    """Compute the destination path: output_root/YYYY/MM/filename.

    With `date_source == "parent_dir"` only the year is known, so the file goes
    to `output_root/YYYY/unknown/filename`. `dest_name` overrides the filename
    used (e.g. the corrected name from `effective_media_name`); pure path math,
    no I/O.
    """
    name = dest_name if dest_name is not None else media_path.name
    if not dt:
        return output_root / "needs_review" / name
    if date_source == "parent_dir":
        return output_root / f"{dt.year:04d}" / "unknown" / name
    return output_root / f"{dt.year:04d}" / f"{dt.month:02d}" / name


def resolve_collision(dest_path: Path) -> Path:
    """If dest_path exists, append _2, _3, etc. before the extension."""
    if not dest_path.exists():
        return dest_path

    stem = dest_path.stem
    ext = dest_path.suffix
    parent = dest_path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def sniffed_rename_old_path(media_path: Path, dest_path: Path) -> Optional[Path]:
    """Return the wrongly-named path a sniffed-rename resume would recover.

    If media_path's name differs from dest_path's (sniffed rename) and a file
    exists at media_path's original name while dest_path does not yet exist,
    return that old-name path; otherwise return None. Pure guard, no I/O
    beyond existence checks, so it is safe for dry-run detection.
    """
    if media_path.name == dest_path.name:
        return None
    old = dest_path.parent / media_path.name
    if dest_path.exists() or not old.exists():
        return None
    return old


def fix_rename_resume(media_path: Path, dest_path: Path) -> None:
    """If dest_path's name differs from media_path's (sniffed rename), and an
    old wrongly-named file exists at media_path's original name while
    dest_path does not yet exist, rename it (and its sidecar) in place.

    Pure guard: returns immediately when names match, dest already exists, or
    the old-name file is absent.
    """
    old = sniffed_rename_old_path(media_path, dest_path)
    if old is None:
        return
    old.rename(dest_path)
    old_sidecar = old.parent / (old.name + ".json")
    sidecar_dest = dest_path.parent / (dest_path.name + ".json")
    if old_sidecar.exists() and not sidecar_dest.exists():
        old_sidecar.rename(sidecar_dest)


def is_already_copied(source: Path, dest: Path) -> bool:
    """Check if file was already copied (same name + same size = skip for resume)."""
    if not dest.exists():
        return False
    try:
        return source.stat().st_size == dest.stat().st_size
    except OSError:
        return False


def copy_with_sidecar(
    media_path: Path,
    json_path: Optional[Path],
    dest_path: Path,
    dry_run: bool,
) -> Path:
    """Copy media file (and its JSON sidecar) to dest_path. Returns actual dest used.

    Several media files may share one sidecar via fallback matching (e.g.
    `foo(1).jpg` inheriting `foo.jpg`'s JSON). Each copied file gets its own
    renamed JSON alongside — this copy-per-inheriting-file behavior is intended
    (resolves the open question in plan 0002).
    """
    dest_path = resolve_collision(dest_path)

    if not dry_run:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_path, dest_path)

        # Copy JSON sidecar alongside, renamed to match the dest filename
        if json_path and json_path.exists():
            json_dest = dest_path.parent / (dest_path.name + ".json")
            shutil.copy2(json_path, json_dest)

    return dest_path
