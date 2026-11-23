"""The ``photree gallery metadata set`` command."""

from collections.abc import Callable
from typing import Annotated

import typer

from photree.clihelpers.options import GALLERY_DIR_OPTION, GALLERY_LINK_MODE_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import no_fields_error
from photree.common.formatting import indent
from photree.common.fs import display_path
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryMetadata,
    load_gallery_metadata,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.gallery.cli.face_ops import require_valid_threshold
from photree.gallery.cli.metadata.app import app


@app.command("set")
def set_cmd(
    ctx: typer.Context,
    gallery_dir: GALLERY_DIR_OPTION = None,
    link_mode: GALLERY_LINK_MODE_OPTION = None,
    faces_enabled: Annotated[
        bool | None,
        typer.Option(
            "--faces-enabled/--no-faces-enabled",
            help=(
                "Enable or disable face detection and clustering during "
                "gallery refresh."
            ),
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
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
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
        raise no_fields_error(
            ("--link-mode", "--faces-enabled", "--face-cluster-threshold"),
        )
    require_valid_threshold(face_cluster_threshold, "--face-cluster-threshold")

    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
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
                f"Updated {display_path(gallery_yaml_path, cwd)}",
                *(indent(line) for line in _changed_fields(current, updated)),
            ],
        ),
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
