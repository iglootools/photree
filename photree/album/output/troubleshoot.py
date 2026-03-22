"""Troubleshooting suggestions for album integrity issues."""

from __future__ import annotations

from textwrap import dedent

from ..integrity import IosAlbumIntegrityResult


def suggest_fixes(
    integrity: IosAlbumIntegrityResult,
    album_dir_flag: str,
) -> list[str]:
    """Suggest fix-ios commands based on integrity check failures."""
    heic = integrity.combined_heic
    mov = integrity.combined_mov
    jpeg = integrity.jpeg

    has_combined_issues = (
        heic.missing
        or heic.wrong_source
        or heic.size_mismatches
        or heic.checksum_mismatches
        or mov.missing
        or mov.wrong_source
        or mov.size_mismatches
        or mov.checksum_mismatches
    )
    has_combined_extra = heic.extra or mov.extra
    has_jpeg_missing = bool(jpeg.missing)
    has_jpeg_extra = bool(jpeg.extra)
    has_orphan_sidecars = bool(integrity.sidecars.orphan_sidecars)
    has_duplicate_numbers = bool(integrity.duplicate_numbers)
    has_miscategorized = bool(integrity.miscategorized)

    return [
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --refresh-combined --dry-run
                      Rebuild main-img/ and main-vid/ from orig/edited sources,
                      then regenerate main-jpg/. Use when main files are missing,
                      corrupted, or out of sync with their sources.""")
            ]
            if has_combined_issues
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --refresh-jpeg --dry-run
                      Regenerate main-jpg/ from main-img/. Use when JPEG files
                      are missing but main-img/ is correct.

                    photree album fix-ios {album_dir_flag} --rm-upstream --dry-run
                      Alternatively, if you intentionally deleted files from main-jpg/,
                      propagate those deletions to main-img/, edit-img/, and orig-img/.""")
            ]
            if has_jpeg_missing and not has_combined_issues
            else []
        ),
        *(
            [
                dedent(f"""\
                    photree album fix-ios {album_dir_flag} --rm-orphan --dry-run
                      Remove edited and main files that have no corresponding orig file.
                      Use when extra files appear in main directories that don't belong.""")
            ]
            if has_combined_extra or has_jpeg_extra
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
