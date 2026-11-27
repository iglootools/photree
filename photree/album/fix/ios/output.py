"""Text the CLI prints for the iOS fixes' results."""

from photree.album.fix.ios import FixIosMiscategorizedResult, FixIosResult
from photree.album.fix.ios.miscategorized import MiscategorizedAction
from photree.album.fix.output import format_removal_summary
from photree.common.formatting import format_dry_run


def rm_orphan_sidecar_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    dry_run: bool = False,
) -> str:
    """Return the line reporting the orphan sidecars removed, or that none were."""
    return format_removal_summary(
        removed_by_dir,
        what="orphan sidecar(s)",
        none_found="No orphan sidecars found.",
        dry_run=dry_run,
    )


def prefer_higher_quality_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    dry_run: bool = False,
) -> str:
    """Return the line reporting the lower-quality duplicates removed, or none."""
    return format_removal_summary(
        removed_by_dir,
        what="lower-quality duplicate(s)",
        none_found="No duplicates found.",
        dry_run=dry_run,
    )


def miscategorized_summary(
    action: MiscategorizedAction,
    heic_from_orig: int,
    heic_from_rendered: int,
    mov_from_orig: int,
    mov_from_rendered: int,
    *,
    dry_run: bool = False,
) -> str:
    """Return the line reporting the miscategorized files moved or removed."""
    total = heic_from_orig + heic_from_rendered + mov_from_orig + mov_from_rendered
    if total == 0:
        return (
            "No miscategorized files found."
            if dry_run
            else "Done. No miscategorized files found."
        )
    verb = "move" if action == MiscategorizedAction.MV else "remove"
    parts = ", ".join(
        [
            *(
                [f"{heic_from_orig} edited file(s) from orig-img"]
                if heic_from_orig
                else []
            ),
            *(
                [f"{heic_from_rendered} original file(s) from edit-img"]
                if heic_from_rendered
                else []
            ),
            *(
                [f"{mov_from_orig} edited file(s) from orig-vid"]
                if mov_from_orig
                else []
            ),
            *(
                [f"{mov_from_rendered} original file(s) from edit-vid"]
                if mov_from_rendered
                else []
            ),
        ],
    )
    return (
        f"Would {verb} {total} miscategorized file(s): {parts}."
        if dry_run
        else f"Done. {verb.capitalize()}d {total} miscategorized file(s): {parts}."
    )


def _miscategorized_line(mc: FixIosMiscategorizedResult, *, dry_run: bool) -> str:
    return miscategorized_summary(
        action=mc.action,
        heic_from_orig=mc.heic_from_orig,
        heic_from_rendered=mc.heic_from_rendered,
        mov_from_orig=mc.mov_from_orig,
        mov_from_rendered=mc.mov_from_rendered,
        dry_run=dry_run,
    )


def format_fix_ios_result(result: FixIosResult, *, dry_run: bool = False) -> list[str]:
    """
    Every requested operation produces a line, including "nothing found".

    Each line of a dry run carries the ``[dry-run]`` label, since a batch
    prints them apart from its own labelled summary.
    """
    sidecars = result.rm_orphan_sidecar_removed_by_dir
    dups = result.prefer_higher_quality_removed_by_dir
    miscategorized = result.miscategorized_result
    lines = [
        *(
            ["No iOS media sources found; nothing to fix."]
            if result.no_ios_media_sources
            else []
        ),
        *(
            [rm_orphan_sidecar_summary(sidecars, dry_run=dry_run)]
            if sidecars is not None
            else []
        ),
        *(
            [prefer_higher_quality_summary(dups, dry_run=dry_run)]
            if dups is not None
            else []
        ),
        *(
            [_miscategorized_line(miscategorized, dry_run=dry_run)]
            if miscategorized is not None
            else []
        ),
    ]
    return [format_dry_run(line, dry_run=dry_run) for line in lines]
