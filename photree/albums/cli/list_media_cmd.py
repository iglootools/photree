"""``photree albums list-media`` command."""

from __future__ import annotations

from ...clihelpers.options import OUTPUT_FILE_OPTION, OUTPUT_FORMAT_OPTION, OutputFormat
from ..batchcli.listmedia import run_batch_list_media
from ..batchcli.resolution import resolve_check_batch_albums
from . import AlbumDirOption, DirOption, albums_app


@albums_app.command("list-media")
def list_media_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    output_format: OUTPUT_FORMAT_OPTION = OutputFormat.TEXT,
    output_file: OUTPUT_FILE_OPTION = None,
) -> None:
    """List all media items across multiple albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_media(
        albums,
        display_base,
        output_format=output_format,
        output_file=output_file,
    )
