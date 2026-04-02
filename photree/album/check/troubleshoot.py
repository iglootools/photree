"""Troubleshooting suggestions for album integrity issues."""

from __future__ import annotations

import shlex
from collections import defaultdict
from textwrap import dedent, indent

from rich.markup import escape

from ..naming import ExifMismatch
from .ios import IosAlbumIntegrityResult


def suggest_fixes(
    integrity: IosAlbumIntegrityResult,
    album_dir_flag: str,
) -> list[str]:
    """Suggest fix commands based on integrity check failures."""
    heic = integrity.browsable_heic
    mov = integrity.browsable_mov
    jpeg = integrity.jpeg

    has_browsable_issues = (
        heic.missing
        or heic.wrong_source
        or heic.size_mismatches
        or heic.checksum_mismatches
        or mov.missing
        or mov.wrong_source
        or mov.size_mismatches
        or mov.checksum_mismatches
    )
    has_browsable_extra = heic.extra or mov.extra
    has_jpeg_missing = bool(jpeg.missing)
    has_jpeg_extra = bool(jpeg.extra)
    has_orphan_sidecars = bool(integrity.sidecars.orphan_sidecars)
    has_duplicate_numbers = bool(integrity.duplicate_numbers)
    has_miscategorized = bool(integrity.miscategorized)

    return [
        *(
            [
                dedent(f"""\
                    photree album fix {album_dir_flag} --refresh-browsable --dry-run
                      Rebuild main-img/ and main-vid/ from orig/edited sources,
                      then regenerate main-jpg/. Use when main files are missing,
                      corrupted, or out of sync with their sources.""")
            ]
            if has_browsable_issues
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix {album_dir_flag} --refresh-jpeg --dry-run
                      Regenerate main-jpg/ from main-img/. Use when JPEG files
                      are missing but main-img/ is correct.

                    photree album fix {album_dir_flag} --rm-upstream --dry-run
                      Alternatively, if you intentionally deleted files from main-jpg/,
                      propagate those deletions to main-img/, edit-img/, and orig-img/.""")
            ]
            if has_jpeg_missing and not has_browsable_issues
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix {album_dir_flag} --rm-orphan --dry-run
                      Remove edited and main files that have no corresponding orig file.
                      Use when extra files appear in main directories that don't belong.""")
            ]
            if has_browsable_extra or has_jpeg_extra
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --rm-orphan-sidecar --dry-run
                      Remove AAE sidecar files that have no matching media file in
                      orig-img/, orig-vid/, edit-img/, or edit-vid/.""")
            ]
            if has_orphan_sidecars
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --prefer-higher-quality-when-dups --dry-run
                      Remove lower-quality duplicates (e.g. JPG when DNG or HEIC exists).
                      Use when multiple format variants exist for the same image number.""")
            ]
            if has_duplicate_numbers
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --rm-miscategorized-safe --dry-run
                      Move files to the correct directory (e.g. edited files from orig-img/
                      to edit-img/). Use --rm-miscategorized to delete them without guaranteering that they are already in the correct directory, or --mv-miscategorized to move them.""")
            ]
            if has_miscategorized
            else []
        ),
    ]


def suggest_exif_fixes(
    mismatches: tuple[ExifMismatch, ...],
    *,
    album_date: str,
    album_dir: str,
) -> list[str]:
    """Generate fix, move, and rm command suggestions for EXIF mismatches."""
    by_date: defaultdict[str, list[ExifMismatch]] = defaultdict(list)
    for m in mismatches:
        date = m.timestamp.split("T")[0] if "T" in m.timestamp else "unknown"
        by_date[date].append(m)

    def _expand_date(d: str) -> str:
        """Expand a partial or range date to YYYY-MM-DD for exiftool."""
        # For ranges, use the start date
        base = d.split("--")[0]
        parts = base.split("-")
        if len(parts) == 1:  # YYYY
            return f"{parts[0]}-01-01"
        elif len(parts) == 2:  # YYYY-MM
            return f"{parts[0]}-{parts[1]}-01"
        else:  # YYYY-MM-DD
            return base

    exif_date = _expand_date(album_date)

    def _sh(path: str) -> str:
        """Shell-quote a path, then escape for Rich markup."""
        return escape(shlex.quote(path))

    def _commands_for_date(date: str, items: list[ExifMismatch]) -> str:
        file_names = [m.file_name for m in items]
        escaped_files = " ".join(_sh(f) for f in file_names)

        # Collect upstream source files for the exiftool fix command
        # Exclude .AAE sidecars — they don't contain EXIF dates
        upstream = sorted(
            f for m in items for f in m.upstream_files if not f.lower().endswith(".aae")
        )
        upstream_paths = " ".join(_sh(f"{album_dir}/{f}") for f in upstream)

        fix_lines = (
            [
                "# fix: set EXIF date on upstream source files",
                f"photree album fix-exif --set-date {exif_date} {upstream_paths}",
            ]
            if upstream
            else [
                "# fix: set EXIF date (no upstream files found, fixing in place)",
                f"photree album fix-exif --set-date {exif_date} "
                + " ".join(_sh(f"{album_dir}/{f}") for f in file_names),
            ]
        )

        rebuild_lines = [
            "# rebuild: recreate main dirs from archival + regenerate JPEGs",
            f"photree album optimize --album-dir {_sh(album_dir)}",
            f"photree album fix --album-dir {_sh(album_dir)} --refresh-jpeg",
        ]

        move_rm_lines = [
            "# move: move files to another album (remove --dry-run to apply)",
            f"photree album mv-media --dry-run -s {_sh(album_dir)}"
            f" -d DEST_ALBUM {escaped_files}",
            "# rm: remove files from this album (remove --dry-run to apply)",
            f"photree album rm-media --dry-run -a {_sh(album_dir)} {escaped_files}",
        ]

        return "\n".join(
            [
                f"# {date} ({len(items)} file(s)):",
                *fix_lines,
                *rebuild_lines,
                *move_rm_lines,
            ]
        )

    return "\n".join(
        [
            "  Suggested commands:",
            *(
                indent(_commands_for_date(date, items), "    ")
                for date, items in sorted(by_date.items())
            ),
        ]
    ).splitlines()
