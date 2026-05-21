"""``photree gallery check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...album.faces.protocol import FACES_DIR
from ...album.store.album_discovery import discover_albums
from ...album.store.metadata import load_album_metadata
from ...albums.cli.batch_ops import run_batch_check
from ...albums.cli.ops import resolve_check_batch_albums
from ...clihelpers.console import console
from ...collection.check import check_all_collections
from ...common.formatting import CHECK, CROSS
from ...common.fs import display_path
from ...clihelpers.options import (
    CHECK_DATE_PART_COLLISION_OPTION,
    CHECK_EXIF_DATE_MATCH_OPTION,
    CHECK_NAMING_OPTION,
    CHECKSUM_OPTION,
    FATAL_EXIF_DATE_MATCH_OPTION,
    FATAL_SIDECAR_OPTION,
    FATAL_WARNINGS_OPTION,
)
from ...fsprotocol import ALBUMS_DIR, PHOTREE_DIR
from ..faces.manifest import (
    compute_npz_checksum,
    load_checksums,
    load_clusters,
    load_manifest,
)
from ..faces.protocol import FaceClusteringResult
from .ops import resolve_gallery_or_exit


@gallery_app.command("check")
def check_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
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
    """Check all albums and collections in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_check(
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
    )

    _check_collections(resolved)
    _check_face_clusters(resolved)


# ---------------------------------------------------------------------------
# Collection checks
# ---------------------------------------------------------------------------


def _check_collections(gallery_dir: Path) -> None:
    """Run collection checks and print results."""
    from ...clihelpers.progress import run_with_spinner

    cwd = Path.cwd()
    col_results = run_with_spinner(
        "Checking collections...",
        lambda: check_all_collections(gallery_dir),
    )
    if not col_results:
        return

    typer.echo("\nCollections:")
    col_failed = sum(1 for r in col_results if not r.success)

    for result in col_results:
        name = display_path(result.collection_dir, cwd)
        if result.success:
            console.print(f"{CHECK} {name}")
        else:
            console.print(f"{CROSS} {name}")
            for issue in result.issues:
                typer.echo(f"    {issue.message}")

    if col_failed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Face cluster checks
# ---------------------------------------------------------------------------


def _check_face_clusters(gallery_dir: Path) -> None:
    """Validate face cluster manifest consistency."""
    from ...clihelpers.progress import run_with_spinner

    def _run_check() -> tuple[FaceClusteringResult | None, list[str]]:
        manifest = load_manifest(gallery_dir)
        clusters = load_clusters(gallery_dir)
        if manifest is None or clusters is None:
            return None, []
        return clusters, [
            *_check_face_index_bounds(clusters, len(manifest.faces)),
            *_check_face_count_consistency(clusters, len(manifest.faces)),
            *_check_album_checksums(gallery_dir),
        ]

    typer.echo("\nFace clusters:")
    clusters, issues = run_with_spinner("Checking face clusters...", _run_check)

    if clusters is None:
        return

    if issues:
        console.print(f"{CROSS} face clusters ({len(issues)} issue(s))")
        for issue in issues:
            typer.echo(f"    {issue}")
        typer.echo("    Run 'photree gallery cluster-faces --redetect' to rebuild.")
        raise typer.Exit(code=1)
    else:
        console.print(
            f"{CHECK} face clusters "
            f"({clusters.face_count} face(s),"
            f" {clusters.cluster_count} cluster(s))"
        )


def _check_face_index_bounds(
    clusters: FaceClusteringResult, manifest_size: int
) -> list[str]:
    """Check that all face indices in clusters are within manifest bounds."""
    return [
        f"cluster {cluster.id[:12]}...: {len(oob)} face index(es) out of bounds"
        for cluster in clusters.clusters
        for oob in [
            [idx for idx in cluster.face_indices if idx < 0 or idx >= manifest_size]
        ]
        if oob
    ]


def _check_face_count_consistency(
    clusters: FaceClusteringResult, manifest_size: int
) -> list[str]:
    """Check that clusters.face_count matches manifest size."""
    return (
        [
            f"face count mismatch: clusters.yaml says {clusters.face_count}, "
            f"manifest has {manifest_size}"
        ]
        if clusters.face_count != manifest_size
        else []
    )


def _check_album_checksums(gallery_dir: Path) -> list[str]:
    """Check that album face data checksums match the gallery index."""
    stored_checksums = load_checksums(gallery_dir)
    if stored_checksums is None:
        return []

    albums_dir = gallery_dir / ALBUMS_DIR
    return [
        issue
        for album_dir in discover_albums(albums_dir)
        for issue in _check_single_album_checksums(album_dir, stored_checksums.albums)
    ]


def _check_single_album_checksums(
    album_dir: Path,
    stored_albums: dict[str, dict[str, str]],
) -> list[str]:
    """Check face data checksums for a single album."""
    meta = load_album_metadata(album_dir)
    if meta is None:
        return []

    faces_dir = album_dir / PHOTREE_DIR / FACES_DIR
    if not faces_dir.is_dir():
        return []

    album_checksums = stored_albums.get(meta.id, {})
    return [
        issue
        for npz_file in sorted(faces_dir.glob("*.npz"))
        for issue in [
            _checksum_issue(meta.id, npz_file.stem, album_checksums, npz_file)
        ]
        if issue is not None
    ]


def _checksum_issue(
    album_id: str,
    ms_name: str,
    album_checksums: dict[str, str],
    npz_file: Path,
) -> str | None:
    """Return an issue string if a checksum is missing or mismatched."""
    stored = album_checksums.get(ms_name)
    prefix = f"album {album_id[:12]}.../{ms_name}"
    match stored:
        case None:
            return f"{prefix}: face data not in gallery index"
        case ck if ck != compute_npz_checksum(npz_file):
            return f"{prefix}: checksum mismatch (album face data changed)"
        case _:
            return None
