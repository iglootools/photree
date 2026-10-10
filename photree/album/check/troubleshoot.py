"""Troubleshooting suggestions for album integrity issues."""

from __future__ import annotations

import shlex
from collections import defaultdict
from textwrap import dedent

from rich.markup import escape

from ...common.formatting import indent
from ..naming import ExifMismatch
from ..store.protocol import MediaSource
from .ios import IosMediaSourceIntegrityResult
from .std import StdMediaSourceIntegrityResult

# ---------------------------------------------------------------------------
# Integrity fixes
# ---------------------------------------------------------------------------


def _has_browsable_issues(
    integrity: IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult,
) -> bool:
    return any(
        check.missing
        or check.wrong_source
        or check.size_mismatches
        or check.checksum_mismatches
        for check in (integrity.browsable_img, integrity.browsable_vid)
    )


def _refresh_browsable(flag: str, ms: MediaSource) -> str:
    return dedent(f"""\
        photree album refresh {flag} --refresh-browsable --dry-run
          Rebuild {ms.img_dir}/ and {ms.vid_dir}/ from orig/edited sources,
          then regenerate {ms.jpg_dir}/. Use when files are missing,
          corrupted, or out of sync with their sources.""")


def _refresh_jpeg(flag: str, ms: MediaSource) -> str:
    return dedent(f"""\
        photree album refresh {flag} --refresh-jpeg --dry-run
          Regenerate {ms.jpg_dir}/ from {ms.img_dir}/. Use when JPEG files
          are missing but {ms.img_dir}/ is correct.

        photree album fix {flag} --rm-upstream --dry-run
          Alternatively, if you intentionally deleted files from {ms.jpg_dir}/,
          propagate those deletions to {ms.img_dir}/, edit-img/, and orig-img/.""")


def _rm_orphan(flag: str) -> str:
    return dedent(f"""\
        photree album fix {flag} --rm-orphan --dry-run
          Remove edited and browsable files that have no corresponding orig file.
          Use when extra files appear in browsable directories that don't belong.""")


def _common_suggestions(
    integrity: IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult,
    flag: str,
    ms: MediaSource,
) -> list[str]:
    """Suggestions for the browsable/JPEG checks every media source has."""
    browsable_issues = _has_browsable_issues(integrity)
    jpeg = integrity.browsable_jpg
    has_extra = bool(
        integrity.browsable_img.extra or integrity.browsable_vid.extra or jpeg.extra
    )
    return [
        *([_refresh_browsable(flag, ms)] if browsable_issues else []),
        *([_refresh_jpeg(flag, ms)] if jpeg.missing and not browsable_issues else []),
        *([_rm_orphan(flag)] if has_extra else []),
    ]


def _ios_suggestions(integrity: IosMediaSourceIntegrityResult, flag: str) -> list[str]:
    """Suggestions for the iOS-only checks (sidecars, numbers, categorization)."""
    return [
        *(
            [
                dedent(f"""\
                    photree album fix-ios {flag} --rm-orphan-sidecar --dry-run
                      Remove AAE sidecar files that have no matching media file in
                      orig-img/, orig-vid/, edit-img/, or edit-vid/.""")
            ]
            if integrity.sidecars.orphan_sidecars
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {flag} --prefer-higher-quality-when-dups --dry-run
                      Remove lower-quality duplicates (e.g. JPG when DNG or HEIC exists).
                      Use when multiple format variants exist for the same image number.""")
            ]
            if integrity.duplicate_numbers
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {flag} --rm-miscategorized-safe --dry-run
                      Delete files from the wrong directory (e.g. edited files in
                      orig-img/) when they already exist in the correct one. Use
                      --rm-miscategorized to delete them without guaranteeing that
                      they are already in the correct directory, or
                      --mv-miscategorized to move them.""")
            ]
            if integrity.miscategorized
            else []
        ),
    ]


def _std_suggestions(
    integrity: StdMediaSourceIntegrityResult, flag: str, ms: MediaSource
) -> list[str]:
    """Suggestions for the std-only checks (duplicate stems)."""
    dirs = ", ".join(sorted({f"{d.directory}/" for d in integrity.duplicate_stems}))
    return (
        [
            dedent(f"""\
                Remove or rename the files sharing a stem in {ms.archive_dir}
                ({dirs}): std sources match variants by filename stem, so each
                stem must be unique within a directory. Then run:
                photree album refresh {flag} --refresh-browsable --dry-run""")
        ]
        if integrity.duplicate_stems
        else []
    )


def suggest_fixes(
    integrity: IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult,
    album_dir_flag: str,
    media_source: MediaSource,
) -> list[str]:
    """Suggest fix commands based on integrity check failures."""
    common = _common_suggestions(integrity, album_dir_flag, media_source)
    match integrity:
        case IosMediaSourceIntegrityResult():
            return [*common, *_ios_suggestions(integrity, album_dir_flag)]
        case StdMediaSourceIntegrityResult():
            return [
                *common,
                *_std_suggestions(integrity, album_dir_flag, media_source),
            ]


# ---------------------------------------------------------------------------
# EXIF fixes
# ---------------------------------------------------------------------------


def _expand_date(d: str) -> str:
    """Expand a partial or range date to YYYY-MM-DD for exiftool."""
    # For ranges, use the start date
    base = d.split("--")[0]
    match base.split("-"):
        case [year]:
            return f"{year}-01-01"
        case [year, month]:
            return f"{year}-{month}-01"
        case _:
            return base


def _sh(path: str) -> str:
    """Shell-quote a path, then escape for Rich markup."""
    return escape(shlex.quote(path))


def _fix_lines(
    items: list[ExifMismatch], *, exif_date: str, album_dir: str
) -> list[str]:
    # Collect upstream source files for the exiftool fix command
    # Exclude .AAE sidecars — they don't contain EXIF dates
    upstream = sorted(
        f for m in items for f in m.upstream_files if not f.lower().endswith(".aae")
    )
    if upstream:
        return [
            "# fix: set EXIF date on upstream source files",
            f"photree album fix-exif --set-date {exif_date} "
            + " ".join(_sh(f"{album_dir}/{f}") for f in upstream),
        ]
    else:
        return [
            "# fix: set EXIF date (no upstream files found, fixing in place)",
            f"photree album fix-exif --set-date {exif_date} "
            + " ".join(_sh(f"{album_dir}/{m.file_name}") for m in items),
        ]


def _commands_for_date(
    date: str, items: list[ExifMismatch], *, exif_date: str, album_dir: str
) -> str:
    escaped_files = " ".join(_sh(m.file_name) for m in items)
    return "\n".join(
        [
            f"# {date} ({len(items)} file(s)):",
            *_fix_lines(items, exif_date=exif_date, album_dir=album_dir),
            "# rebuild: recreate browsable dirs from archival + regenerate JPEGs",
            f"photree album refresh --album-dir {_sh(album_dir)} --refresh-browsable",
            "# move: move files to another album (remove --dry-run to apply)",
            (
                f"photree album mv-media --dry-run -s {_sh(album_dir)}"
                f" -d DEST_ALBUM {escaped_files}"
            ),
            "# rm: remove files from this album (remove --dry-run to apply)",
            f"photree album rm-media --dry-run -a {_sh(album_dir)} {escaped_files}",
        ]
    )


def suggest_exif_fixes(
    mismatches: tuple[ExifMismatch, ...],
    *,
    album_date: str,
    album_dir: str,
) -> list[str]:
    """Generate fix, move, and rm command suggestions for EXIF mismatches.

    Returns unindented lines (commands nested one level under the heading);
    the caller indents the block.
    """
    by_date: defaultdict[str, list[ExifMismatch]] = defaultdict(list)
    for m in mismatches:
        date = m.timestamp.split("T")[0] if "T" in m.timestamp else "unknown"
        by_date[date].append(m)

    exif_date = _expand_date(album_date)
    return "\n".join(
        [
            "Suggested commands:",
            *(
                indent(
                    _commands_for_date(
                        date, items, exif_date=exif_date, album_dir=album_dir
                    )
                )
                for date, items in sorted(by_date.items())
            ),
        ]
    ).splitlines()
