"""Text the CLI prints for the generic fixes' results."""

from photree.album.fix import FixResult, FixRmUpstreamResult
from photree.album.fix.rm_upstream import RmUpstreamSkip, SignalSkipReason


def rm_upstream_summary(
    heic_jpeg: int,
    heic_browsable: int,
    heic_rendered: int,
    heic_orig: int,
    mov_rendered: int,
    *,
    mov_orig: int,
    dry_run: bool = False,
) -> str:
    """Return the line reporting the files rm-upstream removed, per directory."""
    parts = ", ".join(
        [
            *(
                [
                    (
                        f"heic: {heic_jpeg} jpeg, {heic_browsable} main, "
                        f"{heic_rendered} edit, {heic_orig} orig"
                    ),
                ]
                if heic_jpeg or heic_browsable or heic_rendered or heic_orig
                else []
            ),
            *(
                [f"mov: {mov_rendered} edit, {mov_orig} orig"]
                if mov_rendered or mov_orig
                else []
            ),
        ],
    )
    match (bool(parts), dry_run):
        case (True, True):
            return f"Would remove {parts}."
        case (True, False):
            return f"Done. Removed {parts}."
        case (False, True):
            return "Nothing to remove."
        case _:
            return "Done. Nothing to remove."


def rm_upstream_skip_line(skip: RmUpstreamSkip) -> str:
    """Explain why a browsable directory was not used as a deletion signal."""
    match skip.reason:
        case SignalSkipReason.MISSING:
            why = "directory is missing"
        case SignalSkipReason.NO_EXPECTED_FILES:
            why = "directory holds none of its expected files (use --force if intended)"
    return f"Skipped {skip.directory} as a deletion signal: {why}."


def format_removal_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    what: str,
    none_found: str,
    dry_run: bool = False,
) -> str:
    """
    Return the line reporting the files a fix removed, per directory.

    *what* names the removed files (``"orphan(s)"``), and *none_found* is the
    sentence printed when there were none.
    """
    total = sum(len(files) for _, files in removed_by_dir)
    if total == 0:
        return none_found if dry_run else f"Done. {none_found}"
    parts = ", ".join(f"{len(files)} from {name}" for name, files in removed_by_dir)
    return (
        f"Would remove {total} {what}: {parts}."
        if dry_run
        else f"Done. Removed {total} {what}: {parts}."
    )


def rm_orphan_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    dry_run: bool = False,
) -> str:
    """Return the line reporting the orphans removed, or that none were found."""
    return format_removal_summary(
        removed_by_dir,
        what="orphan(s)",
        none_found="No orphans found.",
        dry_run=dry_run,
    )


def _rm_upstream_lines(ru: FixRmUpstreamResult, *, dry_run: bool) -> list[str]:
    return [
        *(rm_upstream_skip_line(skip) for skip in ru.skipped),
        rm_upstream_summary(
            heic_jpeg=ru.heic_jpeg,
            heic_browsable=ru.heic_browsable,
            heic_rendered=ru.heic_rendered,
            heic_orig=ru.heic_orig,
            mov_rendered=ru.mov_rendered,
            mov_orig=ru.mov_orig,
            dry_run=dry_run,
        ),
    ]


def format_fix_result(result: FixResult, *, dry_run: bool = False) -> list[str]:
    """One line per requested fix; a dry run says what each would remove."""
    return [
        *(
            ["No media sources found; nothing to fix."]
            if result.no_media_sources
            else []
        ),
        *(
            _rm_upstream_lines(result.rm_upstream_result, dry_run=dry_run)
            if result.rm_upstream_result is not None
            else []
        ),
        *(
            [rm_orphan_summary(result.rm_orphan_removed_by_dir, dry_run=dry_run)]
            if result.rm_orphan_removed_by_dir is not None
            else []
        ),
    ]


def batch_fix_summary(fixed: int, failed: int, *, dry_run: bool = False) -> str:
    """Return the closing line for a batch fix or fix-ios, after a blank line."""
    return (
        f"\n{fixed} album(s) would be fixed, {failed} failed."
        if dry_run
        else f"\nDone. {fixed} album(s) fixed, {failed} failed."
    )
