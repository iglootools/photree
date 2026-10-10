"""``photree gallery check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...albums.cli.batch_ops.check import run_batch_check
from ...albums.cli.ops import resolve_check_batch_albums
from ...clihelpers.console import console, err_console
from ...clihelpers.options import (
    CHECK_DATE_PART_COLLISION_OPTION,
    CHECK_EXIF_DATE_MATCH_OPTION,
    CHECK_NAMING_OPTION,
    CHECKSUM_OPTION,
    FATAL_EXIF_DATE_MATCH_OPTION,
    FATAL_SIDECAR_OPTION,
    FATAL_WARNINGS_OPTION,
)
from ...clihelpers.progress import run_with_spinner
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...collection.check import check_all_collections
from ...common.formatting import CHECK, CROSS, indent, markup_escape
from ...common.fs import display_path
from ..faces.check import (
    AlbumFaceDataChanged,
    AlbumFaceDataNotIndexed,
    ClusterIndexOutOfBounds,
    FaceClusterIssue,
    FaceCountMismatch,
    check_face_clusters,
)
from . import gallery_app


@gallery_app.command("check")
def check_cmd(
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    checksum: CHECKSUM_OPTION = True,
    fatal_warnings: FATAL_WARNINGS_OPTION = False,
    fatal_sidecar_arg: FATAL_SIDECAR_OPTION = False,
    fatal_exif_date_match: FATAL_EXIF_DATE_MATCH_OPTION = True,
    check_naming: CHECK_NAMING_OPTION = True,
    check_date_part_collision: CHECK_DATE_PART_COLLISION_OPTION = True,
    check_exif_date_match: CHECK_EXIF_DATE_MATCH_OPTION = True,
    refresh_exif_cache: Annotated[
        bool,
        typer.Option(
            "--refresh-exif-cache",
            help="Refresh the EXIF timestamp cache before checking.",
        ),
    ] = False,
) -> None:
    """Check all albums and collections in the gallery.

    Every phase (albums, collections, face clusters) runs even when an earlier
    one fails, so one invocation reports every problem; the exit code is 1 if
    any phase failed.
    """
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    albums_ok = run_batch_check(
        albums,
        display_base,
        checksum=checksum,
        fatal_warnings=fatal_warnings,
        fatal_sidecar_arg=fatal_sidecar_arg,
        fatal_exif_date_match=fatal_exif_date_match,
        check_naming=check_naming,
        check_date_part_collision=check_date_part_collision,
        check_exif_date_match=check_exif_date_match,
        refresh_exif_cache=refresh_exif_cache,
        exit_on_failure=False,
    )
    cwd = Path.cwd()
    results = [
        albums_ok,
        _check_collections(resolved, cwd),
        _check_faces(resolved, cwd),
    ]
    if not all(results):
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Collection checks
# ---------------------------------------------------------------------------


def _check_collections(gallery_dir: Path, cwd: Path) -> bool:
    """Run collection checks and print results. Returns whether all passed."""
    col_results = run_with_spinner(
        "Checking collections...",
        lambda: check_all_collections(gallery_dir),
    )
    if not col_results:
        return True

    typer.echo("\nCollections:")
    console.print(
        "\n".join(
            line
            for result in col_results
            for icon in [CHECK if result.success else CROSS]
            for line in [
                f"{icon} {markup_escape(display_path(result.collection_dir, cwd))}",
                *(indent(markup_escape(issue.message), 2) for issue in result.issues),
            ]
        )
    )
    failed = [r.collection_dir for r in col_results if not r.success]
    if failed:
        err_console.print(
            "\n".join(
                [
                    "\nTo investigate, run:",
                    *(
                        indent(
                            f"'photree collection check --dir \"{display_path(d, cwd)}\"'"
                        )
                        for d in failed
                    ),
                ]
            ),
            markup=False,
        )
    return not failed


# ---------------------------------------------------------------------------
# Face cluster checks
# ---------------------------------------------------------------------------


def _check_faces(gallery_dir: Path, cwd: Path) -> bool:
    """Validate face cluster consistency. Returns whether it passed."""
    typer.echo("\nFace clusters:")
    result = run_with_spinner(
        "Checking face clusters...", lambda: check_face_clusters(gallery_dir)
    )
    if result is None:
        return True
    if result.success:
        console.print(
            f"{CHECK} face clusters "
            f"({result.clusters.face_count} face(s),"
            f" {result.clusters.cluster_count} cluster(s))"
        )
        return True

    console.print(f"{CROSS} face clusters ({len(result.issues)} issue(s))")
    typer.echo("\n".join(indent(_format_face_issue(i, cwd), 2) for i in result.issues))
    err_console.print(
        indent("Run 'photree gallery cluster-faces --redetect' to rebuild.", 2)
    )
    return False


def _format_face_issue(issue: FaceClusterIssue, cwd: Path) -> str:
    match issue:
        case ClusterIndexOutOfBounds(cluster_id=cluster_id, count=count):
            return f"cluster {cluster_id}: {count} face index(es) out of bounds"
        case FaceCountMismatch(recorded=recorded, manifest_size=size):
            return (
                f"face count mismatch: clusters.yaml says {recorded}, "
                f"manifest has {size}"
            )
        case AlbumFaceDataNotIndexed(album_dir=album_dir, media_source=ms):
            return (
                f"{display_path(album_dir, cwd)} ({ms}): face data not in gallery index"
            )
        case AlbumFaceDataChanged(album_dir=album_dir, media_source=ms):
            return (
                f"{display_path(album_dir, cwd)} ({ms}): checksum mismatch "
                "(album face data changed)"
            )
