"""
Troubleshooting output for a failed album check.

What to rename or run to fix each failure.

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.

Formatters return Rich markup: every user-derived value (album and media
source names, paths, filenames, issue messages) is escaped with
:func:`~photree.common.formatting.markup_escape` here, so callers print the
result with markup enabled and must not escape it again.
"""

from textwrap import dedent

from photree.album.check import AlbumPreflightResult
from photree.album.check.troubleshoot import suggest_fixes
from photree.common.formatting import markup_escape


def media_source_conflicts_troubleshoot(conflicts: tuple[str, ...]) -> str:
    """Return the troubleshooting text for media source name clashes."""
    names = markup_escape(", ".join(conflicts))
    return (
        f"Media source name(s) used by both an iOS and a std archive: {names}.\n"
        "Rename one of the two archive directories (and its browsable "
        "directories) so every media source name is unique."
    )


def _integrity_suggestions(
    result: AlbumPreflightResult,
    album_dir_flag: str,
) -> list[str]:
    """Fix suggestions for every media source's integrity failures (iOS and std)."""
    return [
        suggestion
        for ms, ms_result in (
            result.integrity.by_media_source if result.integrity is not None else ()
        )
        for suggestion in suggest_fixes(ms_result, album_dir_flag, ms)
    ]


def _missing_dirs_suggestions(
    result: AlbumPreflightResult,
    album_dir_flag: str,
) -> list[str]:
    """Missing browsable directories → suggest refresh --refresh-browsable."""
    missing_browsable = frozenset(result.dir_check.missing) & frozenset(
        d
        for ms in result.media_source_summary.media_sources
        for d in (ms.img_dir, ms.vid_dir, ms.jpg_dir)
    )
    return (
        [
            dedent(f"""\
                photree album refresh {album_dir_flag} --refresh-browsable
                  Rebuild browsable directories ({", ".join(sorted(missing_browsable))})
                  from archive sources, then regenerate JPEGs."""),
        ]
        if missing_browsable
        else []
    )


def _media_metadata_suggestions(
    result: AlbumPreflightResult,
    album_dir_flag: str,
) -> list[str]:
    return (
        [
            dedent(f"""\
                photree album refresh {album_dir_flag}
                  Generate or update media IDs in .photree/media-ids/."""),
        ]
        if result.media_metadata_check is not None
        and not result.media_metadata_check.in_sync
        else []
    )


def format_album_preflight_troubleshoot(
    result: AlbumPreflightResult,
    album_dir: str = ".",
) -> str | None:
    """Format troubleshooting for failed album checks, or return None if none failed."""
    album_dir_flag = f'--album-dir "{album_dir}"'
    all_suggestions = [
        *_missing_dirs_suggestions(result, album_dir_flag),
        *_integrity_suggestions(result, album_dir_flag),
        *_media_metadata_suggestions(result, album_dir_flag),
    ]
    lines = [
        *(
            [media_source_conflicts_troubleshoot(result.media_source_conflicts)]
            if result.media_source_conflicts
            else []
        ),
        *(
            [
                "Suggested fixes (remove --dry-run to apply):\n\n"
                # Suggestions are plain text quoting the album dir and media
                # source names, so they are escaped as a whole.
                + "\n\n".join(markup_escape(s) for s in all_suggestions),
            ]
            if all_suggestions
            else []
        ),
    ]
    return "\n".join(lines) if lines else None
