"""``photree gallery metadata set`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_metadata_app
from ....common.fs import display_path
from ....clihelpers.console import err_console
from ....fsprotocol import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    load_gallery_metadata,
    save_gallery_metadata,
)
from ..ops import resolve_gallery_or_exit


@gallery_metadata_app.command("set")
def set_cmd(
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
    link_mode: Annotated[
        Optional[LinkMode],
        typer.Option(
            "--link-mode",
            help="Default link mode for optimize and other link-mode operations.",
        ),
    ] = None,
    faces_enabled: Annotated[
        Optional[bool],
        typer.Option(
            "--faces-enabled",
            help="Enable face detection and clustering during gallery refresh.",
        ),
    ] = None,
    face_cluster_threshold: Annotated[
        Optional[float],
        typer.Option(
            "--face-cluster-threshold",
            help="Cosine distance threshold for face clustering (0.0-1.0).",
        ),
    ] = None,
) -> None:
    """Update gallery metadata fields."""
    if link_mode is None and faces_enabled is None and face_cluster_threshold is None:
        err_console.print(
            "No fields specified. Use --link-mode, --faces-enabled,"
            " or --face-cluster-threshold to set a value."
        )
        raise typer.Exit(code=1)

    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    gallery_yaml_path = resolved / PHOTREE_DIR / GALLERY_YAML
    current = load_gallery_metadata(gallery_yaml_path)

    updated = GalleryMetadata(
        link_mode=link_mode if link_mode is not None else current.link_mode,
        faces_enabled=(
            faces_enabled if faces_enabled is not None else current.faces_enabled
        ),
        face_cluster_threshold=(
            face_cluster_threshold
            if face_cluster_threshold is not None
            else current.face_cluster_threshold
        ),
    )

    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)

    save_gallery_metadata(resolved, updated)
    changes: list[str] = []
    if link_mode is not None and link_mode != current.link_mode:
        changes.append(
            f"  link-mode: {current.link_mode.value} -> {updated.link_mode.value}"
        )
    if faces_enabled is not None and faces_enabled != current.faces_enabled:
        changes.append(
            f"  faces-enabled: {current.faces_enabled} -> {updated.faces_enabled}"
        )
    if (
        face_cluster_threshold is not None
        and face_cluster_threshold != current.face_cluster_threshold
    ):
        changes.append(
            f"  face-cluster-threshold: {current.face_cluster_threshold}"
            f" -> {updated.face_cluster_threshold}"
        )
    typer.echo(f"Updated {display_path(gallery_yaml_path, cwd)}\n" + "\n".join(changes))
