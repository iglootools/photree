"""``photree gallery metadata set`` command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from ....clihelpers.console import err_console
from ....clihelpers.resolution import resolve_gallery_or_exit
from ....common.formatting import indent
from ....common.fs import display_path
from ....fsprotocol import (
    GALLERY_YAML,
    PHOTREE_DIR,
    GalleryMetadata,
    LinkMode,
    load_gallery_metadata,
    save_gallery_metadata,
)
from ..ops import require_valid_threshold
from . import gallery_metadata_app


@gallery_metadata_app.command("set")
def set_cmd(
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
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="Default link mode for refresh and other link-mode operations.",
        ),
    ] = None,
    faces_enabled: Annotated[
        bool | None,
        typer.Option(
            "--faces-enabled",
            help="Enable face detection and clustering during gallery refresh.",
        ),
    ] = None,
    face_cluster_threshold: Annotated[
        float | None,
        typer.Option(
            "--face-cluster-threshold",
            help="Cosine distance threshold for face clustering (0.0-1.0).",
        ),
    ] = None,
) -> None:
    """Update gallery metadata fields."""
    requested = {
        field: value
        for field, value in {
            "link_mode": link_mode,
            "faces_enabled": faces_enabled,
            "face_cluster_threshold": face_cluster_threshold,
        }.items()
        if value is not None
    }
    if not requested:
        err_console.print(
            "No fields specified. Use --link-mode, --faces-enabled,"
            " or --face-cluster-threshold to set a value."
        )
        raise typer.Exit(code=1)
    require_valid_threshold(face_cluster_threshold, "--face-cluster-threshold")

    resolved = resolve_gallery_or_exit(gallery_dir)
    gallery_yaml_path = resolved / PHOTREE_DIR / GALLERY_YAML
    current = load_gallery_metadata(gallery_yaml_path)
    updated = current.model_copy(update=requested)

    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)

    save_gallery_metadata(resolved, updated)
    typer.echo(
        "\n".join(
            [
                f"Updated {display_path(gallery_yaml_path, Path.cwd())}",
                *(indent(line) for line in _changed_fields(current, updated)),
            ]
        )
    )


_FIELDS: tuple[tuple[str, Callable[[GalleryMetadata], object]], ...] = (
    ("link-mode", lambda m: m.link_mode),
    ("faces-enabled", lambda m: m.faces_enabled),
    ("face-cluster-threshold", lambda m: m.face_cluster_threshold),
)


def _changed_fields(before: GalleryMetadata, after: GalleryMetadata) -> list[str]:
    """``<field>: <old> -> <new>`` for every field that changed."""
    return [
        f"{label}: {get(before)} -> {get(after)}"
        for label, get in _FIELDS
        if get(before) != get(after)
    ]
